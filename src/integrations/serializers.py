"""DRF Serializers for ERP Integrations."""
from rest_framework import serializers

from .models import ERPConnection, ERPFieldMapping, ERPSyncLog


class ERPConnectionSerializer(serializers.ModelSerializer):
    """Full connection serializer (hides secret in read)."""

    app_secret = serializers.CharField(write_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = ERPConnection
        fields = [
            "id", "tenant_id", "provider", "name",
            "app_key", "app_secret",
            "is_active", "sync_direction", "auto_sync", "requires_approval",
            "last_sync_at", "last_error", "consecutive_failures", "is_circuit_open",
            "metadata", "status",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "last_sync_at", "last_error", "consecutive_failures",
            "is_circuit_open", "created_at", "updated_at",
        ]

    def get_status(self, obj) -> str:
        if obj.is_circuit_open:
            return "circuit_open"
        if not obj.is_active:
            return "inactive"
        return "healthy"


class ERPConnectionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing connections (no secrets)."""

    status = serializers.SerializerMethodField()

    class Meta:
        model = ERPConnection
        fields = [
            "id", "provider", "name", "is_active", "sync_direction",
            "auto_sync", "requires_approval",
            "last_sync_at", "last_error", "is_circuit_open",
            "status", "created_at",
        ]

    def get_status(self, obj) -> str:
        if obj.is_circuit_open:
            return "circuit_open"
        if not obj.is_active:
            return "inactive"
        return "healthy"


class ERPSyncLogSerializer(serializers.ModelSerializer):
    """Sync log serializer."""

    connection_name = serializers.CharField(source="connection.name", read_only=True)
    provider = serializers.CharField(source="connection.provider", read_only=True)

    class Meta:
        model = ERPSyncLog
        fields = [
            "id", "connection", "connection_name", "provider", "tenant_id",
            "entity_type", "entity_id", "erp_entity_id",
            "direction", "status",
            "request_payload", "response_payload", "error_message",
            "idempotency_key", "correlation_id",
            "approval_id", "approved_by", "approved_at",
            "started_at", "completed_at", "duration_ms",
            "created_at",
        ]
        read_only_fields = fields


class ERPFieldMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ERPFieldMapping
        fields = [
            "id", "connection", "entity_type",
            "docai_field", "erp_field", "transform",
            "default_value", "is_required",
        ]


class TestConnectionSerializer(serializers.Serializer):
    """Input for testing a connection."""

    connection_id = serializers.UUIDField()


class SyncDocumentSerializer(serializers.Serializer):
    """Input for syncing a document to ERP."""

    connection_id = serializers.UUIDField()
    entity_type = serializers.ChoiceField(choices=["conta_pagar", "conta_receber", "cliente"])
    extracted_data = serializers.JSONField()
    correlation_id = serializers.CharField(required=False, default="")
    codigo_cliente_fornecedor = serializers.IntegerField(required=False, allow_null=True, default=None)


class ApproveSyncSerializer(serializers.Serializer):
    """Input for approving a pending sync."""

    sync_log_id = serializers.UUIDField()
    approved_by = serializers.CharField(required=False, default="")
