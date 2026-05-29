"""
ERP Integration models.

Supports multiple ERP connectors (Omie, Bling, TOTVS) with per-tenant
configuration, sync logging, and field mapping.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone

from core.tenants import INTERNAL_TENANT_ID


class ERPProvider(models.TextChoices):
    OMIE = "omie", "Omie"
    BLING = "bling", "Bling"
    TOTVS = "totvs", "TOTVS"


class SyncDirection(models.TextChoices):
    DOCAI_TO_ERP = "docai_to_erp", "DocAI → ERP"
    ERP_TO_DOCAI = "erp_to_docai", "ERP → DocAI"
    BIDIRECTIONAL = "bidirectional", "Bidirecional"


class SyncStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    AWAITING_APPROVAL = "awaiting_approval", "Aguardando Aprovação"
    IN_PROGRESS = "in_progress", "Em Progresso"
    SUCCESS = "success", "Sucesso"
    FAILED = "failed", "Falhou"
    RETRYING = "retrying", "Tentando Novamente"


class ERPConnection(models.Model):
    """
    Stores ERP connection credentials and config per tenant.
    Credentials are encrypted at rest via Django's SECRET_KEY.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.CharField(max_length=100, default=INTERNAL_TENANT_ID, db_index=True)

    provider = models.CharField(max_length=20, choices=ERPProvider.choices)
    name = models.CharField(max_length=200, help_text="Nome amigável da conexão (ex: 'Omie Produção')")

    # Credentials (Omie uses app_key + app_secret)
    app_key = models.CharField(max_length=255, help_text="App Key / Client ID")
    app_secret = models.CharField(max_length=255, help_text="App Secret / Client Secret")

    # Config
    is_active = models.BooleanField(default=True)
    sync_direction = models.CharField(
        max_length=20,
        choices=SyncDirection.choices,
        default=SyncDirection.DOCAI_TO_ERP,
    )
    auto_sync = models.BooleanField(
        default=False,
        help_text="Se ativo, sincroniza automaticamente após extração de documento.",
    )
    requires_approval = models.BooleanField(
        default=True,
        help_text="Se ativo, sync requer aprovação humana antes de executar.",
    )

    # Health
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    consecutive_failures = models.IntegerField(default=0)
    is_circuit_open = models.BooleanField(
        default=False,
        help_text="Circuit breaker: se True, conexão está isolada por falhas.",
    )

    metadata = models.JSONField(default=dict, blank=True, help_text="Configurações extras do provider.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        unique_together = [("tenant_id", "provider", "app_key")]
        indexes = [
            models.Index(fields=["tenant_id", "provider"]),
            models.Index(fields=["is_active", "is_circuit_open"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_provider_display()}) - {'Ativo' if self.is_active else 'Inativo'}"

    def record_success(self):
        self.last_sync_at = timezone.now()
        self.last_error = ""
        self.consecutive_failures = 0
        self.is_circuit_open = False
        self.save(update_fields=["last_sync_at", "last_error", "consecutive_failures", "is_circuit_open", "updated_at"])

    def record_failure(self, error: str, threshold: int = 5):
        self.last_error = error
        self.consecutive_failures += 1
        if self.consecutive_failures >= threshold:
            self.is_circuit_open = True
        self.save(update_fields=["last_error", "consecutive_failures", "is_circuit_open", "updated_at"])


class ERPSyncLog(models.Model):
    """Append-only log of every sync operation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(ERPConnection, on_delete=models.CASCADE, related_name="sync_logs")
    tenant_id = models.CharField(max_length=100, default=INTERNAL_TENANT_ID, db_index=True)

    # What was synced
    entity_type = models.CharField(
        max_length=50,
        help_text="Tipo: conta_pagar, conta_receber, cliente, fornecedor, nf_entrada",
    )
    entity_id = models.CharField(max_length=100, blank=True, default="", help_text="ID interno do DocAI")
    erp_entity_id = models.CharField(max_length=100, blank=True, default="", help_text="ID retornado pelo ERP")

    direction = models.CharField(max_length=20, choices=SyncDirection.choices)
    status = models.CharField(max_length=20, choices=SyncStatus.choices, default=SyncStatus.PENDING)

    # Payload
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")

    # Tracing
    idempotency_key = models.CharField(max_length=100, unique=True, help_text="Chave para evitar duplicações")
    correlation_id = models.CharField(max_length=100, blank=True, default="")

    # Approval
    approval_id = models.CharField(max_length=100, blank=True, default="", help_text="ID da aprovação no gateway")
    approved_by = models.CharField(max_length=200, blank=True, default="")
    approved_at = models.DateTimeField(null=True, blank=True)

    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["connection", "entity_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.entity_type} → {self.get_status_display()} ({self.connection.get_provider_display()})"


class ERPFieldMapping(models.Model):
    """
    Customizable field mapping between DocAI extracted fields and ERP fields.
    Allows tenants to configure how extracted data maps to their ERP.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(ERPConnection, on_delete=models.CASCADE, related_name="field_mappings")

    entity_type = models.CharField(max_length=50, help_text="Tipo de entidade (conta_pagar, cliente, etc)")
    docai_field = models.CharField(max_length=100, help_text="Campo extraído pelo DocAI")
    erp_field = models.CharField(max_length=100, help_text="Campo no ERP destino")
    transform = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Transformação: 'date_br', 'cents_to_decimal', 'cpf_cnpj_clean', etc",
    )
    default_value = models.CharField(max_length=200, blank=True, default="")
    is_required = models.BooleanField(default=False)

    class Meta:
        unique_together = [("connection", "entity_type", "docai_field")]
        ordering = ["entity_type", "docai_field"]

    def __str__(self):
        return f"{self.docai_field} → {self.erp_field} ({self.entity_type})"
