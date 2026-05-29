"""
ERP Sync Service — orchestrates the full sync pipeline.

Flow:
1. Document extracted by DocAI
2. Transformer converts to ERP format
3. (Optional) Approval requested via gateway
4. Connector sends to ERP
5. Result logged in ERPSyncLog
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from django.db import transaction
from django.utils import timezone

from integrations.connectors.base import ERPResponse
from integrations.connectors.omie import OmieConnector
from integrations.models import (
    ERPConnection,
    ERPProvider,
    ERPSyncLog,
    SyncDirection,
    SyncStatus,
)
from integrations.transformers.omie import OmieTransformer

logger = logging.getLogger(__name__)


class ERPSyncError(Exception):
    """Raised when sync fails."""

    def __init__(self, message: str, error_code: str = ""):
        self.error_code = error_code
        super().__init__(message)


def get_connector(connection: ERPConnection):
    """Factory: returns the appropriate connector for a connection."""
    if connection.provider == ERPProvider.OMIE:
        return OmieConnector(
            app_key=connection.app_key,
            app_secret=connection.app_secret,
        )
    raise ERPSyncError(f"Provider '{connection.provider}' not implemented yet", "UNSUPPORTED_PROVIDER")


def check_erp_connection(connection: ERPConnection) -> ERPResponse:
    """Test if an ERP connection is working."""
    if connection.is_circuit_open:
        return ERPResponse(
            success=False,
            error_code="CIRCUIT_OPEN",
            error_message="Connection is isolated due to repeated failures.",
        )
    connector = get_connector(connection)
    return connector.test_connection()


def sync_conta_pagar(
    connection: ERPConnection,
    extracted_data: dict[str, Any],
    correlation_id: str = "",
    codigo_cliente_fornecedor: int | None = None,
    skip_approval: bool = False,
) -> ERPSyncLog:
    """
    Sync an extracted document as Conta a Pagar in the ERP.
    
    Args:
        connection: Active ERPConnection
        extracted_data: DocAI extraction output
        correlation_id: Tracing correlation ID
        codigo_cliente_fornecedor: Omie supplier code (auto-resolves if None)
        skip_approval: Skip approval gateway (for pre-approved operations)
    
    Returns:
        ERPSyncLog with result status
    """
    _validate_connection(connection)

    # Transform
    payload = OmieTransformer.nota_fiscal_to_conta_pagar(
        extracted_data=extracted_data,
        connection_id=str(connection.id),
        codigo_cliente_fornecedor=codigo_cliente_fornecedor,
    )

    # Generate idempotency key
    idempotency_key = f"cp:{connection.id}:{payload['codigo_lancamento_integracao']}"

    # Check if already synced (idempotent)
    existing = ERPSyncLog.objects.filter(idempotency_key=idempotency_key).first()
    if existing and existing.status == SyncStatus.SUCCESS:
        logger.info("Sync already completed: %s", idempotency_key)
        return existing

    # Create log entry
    sync_log = ERPSyncLog.objects.create(
        connection=connection,
        tenant_id=connection.tenant_id,
        entity_type="conta_pagar",
        entity_id=extracted_data.get("document_id", ""),
        direction=SyncDirection.DOCAI_TO_ERP,
        status=SyncStatus.PENDING if skip_approval else SyncStatus.AWAITING_APPROVAL,
        request_payload=payload,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id or str(uuid.uuid4()),
    )

    if not skip_approval and connection.requires_approval:
        logger.info("Sync %s awaiting approval", sync_log.id)
        return sync_log

    # Execute sync
    return _execute_sync(connection, sync_log, payload, "criar_conta_pagar")


def sync_conta_receber(
    connection: ERPConnection,
    extracted_data: dict[str, Any],
    correlation_id: str = "",
    codigo_cliente_fornecedor: int | None = None,
    skip_approval: bool = False,
) -> ERPSyncLog:
    """Sync extracted document as Conta a Receber."""
    _validate_connection(connection)

    payload = OmieTransformer.nota_fiscal_to_conta_receber(
        extracted_data=extracted_data,
        connection_id=str(connection.id),
        codigo_cliente_fornecedor=codigo_cliente_fornecedor,
    )

    idempotency_key = f"cr:{connection.id}:{payload['codigo_lancamento_integracao']}"

    existing = ERPSyncLog.objects.filter(idempotency_key=idempotency_key).first()
    if existing and existing.status == SyncStatus.SUCCESS:
        return existing

    sync_log = ERPSyncLog.objects.create(
        connection=connection,
        tenant_id=connection.tenant_id,
        entity_type="conta_receber",
        entity_id=extracted_data.get("document_id", ""),
        direction=SyncDirection.DOCAI_TO_ERP,
        status=SyncStatus.PENDING if skip_approval else SyncStatus.AWAITING_APPROVAL,
        request_payload=payload,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id or str(uuid.uuid4()),
    )

    if not skip_approval and connection.requires_approval:
        return sync_log

    return _execute_sync(connection, sync_log, payload, "criar_conta_receber")


def sync_cliente(
    connection: ERPConnection,
    extracted_data: dict[str, Any],
    correlation_id: str = "",
) -> ERPSyncLog:
    """
    Sync client/supplier to ERP.
    Client sync does NOT require approval (cadastro only).
    """
    _validate_connection(connection)

    payload = OmieTransformer.documento_to_cliente(extracted_data)
    idempotency_key = f"cli:{connection.id}:{payload['codigo_cliente_integracao']}"

    existing = ERPSyncLog.objects.filter(idempotency_key=idempotency_key).first()
    if existing and existing.status == SyncStatus.SUCCESS:
        return existing

    sync_log = ERPSyncLog.objects.create(
        connection=connection,
        tenant_id=connection.tenant_id,
        entity_type="cliente",
        entity_id=extracted_data.get("cnpj_cpf", ""),
        direction=SyncDirection.DOCAI_TO_ERP,
        status=SyncStatus.PENDING,
        request_payload=payload,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id or str(uuid.uuid4()),
    )

    return _execute_sync(connection, sync_log, payload, "criar_cliente")


def approve_and_execute(sync_log_id: str, approved_by: str = "") -> ERPSyncLog:
    """
    Approve a pending sync and execute it.
    Called by the Approval Gateway after human approval.
    """
    with transaction.atomic():
        sync_log = ERPSyncLog.objects.select_for_update().get(id=sync_log_id)

        if sync_log.status != SyncStatus.AWAITING_APPROVAL:
            raise ERPSyncError(
                f"Sync {sync_log_id} is not awaiting approval (status: {sync_log.status})",
                "INVALID_STATUS",
            )

        sync_log.approved_by = approved_by
        sync_log.approved_at = timezone.now()
        sync_log.save(update_fields=["approved_by", "approved_at"])

    # Determine which operation to execute
    operation_map = {
        "conta_pagar": "criar_conta_pagar",
        "conta_receber": "criar_conta_receber",
        "cliente": "criar_cliente",
    }
    operation = operation_map.get(sync_log.entity_type, "criar_conta_pagar")

    return _execute_sync(sync_log.connection, sync_log, sync_log.request_payload, operation)


def resolve_fornecedor(connection: ERPConnection, cnpj: str) -> int | None:
    """
    Try to find a supplier in Omie by CNPJ. Returns Omie code or None.
    If not found, returns None (caller should create the client first).
    """
    connector = get_connector(connection)
    result = connector.pesquisar_cliente_por_cnpj(cnpj)
    if result.success and result.entity_id:
        return int(result.entity_id)
    return None


# --- Private helpers ---


def _validate_connection(connection: ERPConnection):
    """Validate connection is usable."""
    if not connection.is_active:
        raise ERPSyncError("Connection is inactive", "INACTIVE")
    if connection.is_circuit_open:
        raise ERPSyncError("Connection circuit breaker is open", "CIRCUIT_OPEN")


def _execute_sync(
    connection: ERPConnection,
    sync_log: ERPSyncLog,
    payload: dict,
    operation: str,
) -> ERPSyncLog:
    """Execute the actual sync call and update log."""
    connector = get_connector(connection)

    # Auto-resolve fornecedor if missing for conta_pagar/conta_receber
    if operation in ("criar_conta_pagar", "criar_conta_receber") and not payload.get("codigo_cliente_fornecedor"):
        cnpj = payload.get("_cnpj_emitente") or ""
        fornecedor_code = None
        if cnpj:
            try:
                fornecedor_code = resolve_fornecedor(connection, cnpj)
            except Exception as e:
                logger.warning("Failed to resolve fornecedor for CNPJ %s: %s", cnpj, e)
        if not fornecedor_code:
            # Use default supplier from connection metadata or first available
            fornecedor_code = connection.metadata.get("default_fornecedor_code") if connection.metadata else None
        if fornecedor_code:
            payload["codigo_cliente_fornecedor"] = int(fornecedor_code)
            sync_log.request_payload = payload
            sync_log.save(update_fields=["request_payload"])

    sync_log.status = SyncStatus.IN_PROGRESS
    sync_log.started_at = timezone.now()
    sync_log.save(update_fields=["status", "started_at"])

    start_time = time.time()

    try:
        # Remove internal fields before sending to ERP
        api_payload = {k: v for k, v in payload.items() if not k.startswith("_")}

        # Call the appropriate connector method
        method = getattr(connector, operation)
        result: ERPResponse = method(api_payload)

        duration_ms = int((time.time() - start_time) * 1000)

        if result.success:
            sync_log.status = SyncStatus.SUCCESS
            sync_log.erp_entity_id = result.entity_id
            sync_log.response_payload = result.raw_response or {}
            connection.record_success()
        else:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = result.error_message
            sync_log.response_payload = result.raw_response or {}
            connection.record_failure(result.error_message)

        sync_log.completed_at = timezone.now()
        sync_log.duration_ms = duration_ms
        sync_log.save(update_fields=[
            "status", "erp_entity_id", "response_payload",
            "error_message", "completed_at", "duration_ms",
        ])

        return sync_log

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        sync_log.status = SyncStatus.FAILED
        sync_log.error_message = str(e)
        sync_log.completed_at = timezone.now()
        sync_log.duration_ms = duration_ms
        sync_log.save(update_fields=["status", "error_message", "completed_at", "duration_ms"])
        connection.record_failure(str(e))
        raise ERPSyncError(str(e), "EXECUTION_ERROR") from e
