"""
Celery tasks for async ERP sync operations.

These tasks handle:
- Async sync execution (non-blocking for the API)
- Retry on transient failures
- Batch sync for multiple documents
- Periodic health checks on connections
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from integrations.models import ERPConnection, ERPSyncLog, SyncStatus

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
)
def task_sync_conta_pagar(self, connection_id: str, extracted_data: dict, correlation_id: str = "", skip_approval: bool = False):
    """Async task to sync a document as Conta a Pagar."""
    from integrations.services import sync_conta_pagar

    connection = ERPConnection.objects.get(id=connection_id)
    try:
        result = sync_conta_pagar(
            connection=connection,
            extracted_data=extracted_data,
            correlation_id=correlation_id,
            skip_approval=skip_approval,
        )
        logger.info("Sync conta_pagar completed: %s (status: %s)", result.id, result.status)
        return {"sync_log_id": str(result.id), "status": result.status}
    except Exception as exc:
        logger.error("Sync conta_pagar failed (attempt %d): %s", self.request.retries + 1, str(exc))
        raise


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
)
def task_sync_conta_receber(self, connection_id: str, extracted_data: dict, correlation_id: str = ""):
    """Async task to sync a document as Conta a Receber."""
    from integrations.services import sync_conta_receber

    connection = ERPConnection.objects.get(id=connection_id)
    try:
        result = sync_conta_receber(
            connection=connection,
            extracted_data=extracted_data,
            correlation_id=correlation_id,
            skip_approval=True,
        )
        logger.info("Sync conta_receber completed: %s (status: %s)", result.id, result.status)
        return {"sync_log_id": str(result.id), "status": result.status}
    except Exception as exc:
        logger.error("Sync conta_receber failed (attempt %d): %s", self.request.retries + 1, str(exc))
        raise


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def task_sync_cliente(self, connection_id: str, extracted_data: dict, correlation_id: str = ""):
    """Async task to sync a client/supplier."""
    from integrations.services import sync_cliente

    connection = ERPConnection.objects.get(id=connection_id)
    try:
        result = sync_cliente(
            connection=connection,
            extracted_data=extracted_data,
            correlation_id=correlation_id,
        )
        logger.info("Sync cliente completed: %s (status: %s)", result.id, result.status)
        return {"sync_log_id": str(result.id), "status": result.status}
    except Exception as exc:
        logger.error("Sync cliente failed (attempt %d): %s", self.request.retries + 1, str(exc))
        raise


@shared_task
def task_approve_and_execute(sync_log_id: str, approved_by: str = ""):
    """Execute a previously approved sync."""
    from integrations.services import approve_and_execute

    try:
        result = approve_and_execute(sync_log_id, approved_by)
        logger.info("Approved sync executed: %s (status: %s)", result.id, result.status)
        return {"sync_log_id": str(result.id), "status": result.status}
    except Exception as exc:
        logger.error("Approved sync execution failed: %s - %s", sync_log_id, str(exc))
        raise


@shared_task
def task_retry_failed_syncs(tenant_id: str | None = None):
    """
    Retry failed syncs that haven't exceeded max retries.
    Run periodically via Celery Beat.
    """
    from integrations.services import _execute_sync, get_connector

    queryset = ERPSyncLog.objects.filter(
        status=SyncStatus.FAILED,
        connection__is_active=True,
        connection__is_circuit_open=False,
    )
    if tenant_id:
        queryset = queryset.filter(tenant_id=tenant_id)

    # Only retry recent failures (last 24h)
    cutoff = timezone.now() - timezone.timedelta(hours=24)
    queryset = queryset.filter(created_at__gte=cutoff)

    retried = 0
    for sync_log in queryset[:20]:  # Max 20 retries per run
        operation_map = {
            "conta_pagar": "criar_conta_pagar",
            "conta_receber": "criar_conta_receber",
            "cliente": "criar_cliente",
        }
        operation = operation_map.get(sync_log.entity_type)
        if not operation:
            continue

        try:
            sync_log.status = SyncStatus.RETRYING
            sync_log.save(update_fields=["status"])
            _execute_sync(sync_log.connection, sync_log, sync_log.request_payload, operation)
            retried += 1
        except Exception as exc:
            logger.warning("Retry failed for %s: %s", sync_log.id, str(exc))

    logger.info("Retried %d failed syncs", retried)
    return {"retried": retried}


@shared_task
def task_check_erp_connections():
    """
    Periodic health check for all active ERP connections.
    Resets circuit breaker if connection recovers.
    """
    from integrations.services import check_erp_connection

    connections = ERPConnection.objects.filter(is_active=True)
    results = []

    for conn in connections:
        result = check_erp_connection(conn)
        if result.success and conn.is_circuit_open:
            # Connection recovered — reset circuit breaker
            conn.is_circuit_open = False
            conn.consecutive_failures = 0
            conn.last_error = ""
            conn.save(update_fields=["is_circuit_open", "consecutive_failures", "last_error", "updated_at"])
            logger.info("Connection %s recovered — circuit breaker reset", conn.name)

        results.append({
            "connection": conn.name,
            "provider": conn.provider,
            "healthy": result.success,
            "error": result.error_message if not result.success else "",
        })

    return results
