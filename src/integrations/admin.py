from django.contrib import admin
from django.utils.html import format_html

from .models import ERPConnection, ERPFieldMapping, ERPSyncLog


class ERPFieldMappingInline(admin.TabularInline):
    model = ERPFieldMapping
    extra = 0
    fields = ("entity_type", "docai_field", "erp_field", "transform", "is_required")


@admin.register(ERPConnection)
class ERPConnectionAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "tenant_id", "status_conexao", "circuit_status", "last_sync_at")
    list_filter = ("provider", "is_active", "is_circuit_open", "sync_direction")
    search_fields = ("name", "tenant_id")
    inlines = [ERPFieldMappingInline]
    readonly_fields = ("last_sync_at", "last_error", "consecutive_failures", "created_at", "updated_at")

    @admin.display(description="Conexão")
    def status_conexao(self, obj):
        color = "green" if obj.is_active else "red"
        label = "Ativa" if obj.is_active else "Inativa"
        return format_html('<span style="color: {};">{}</span>', color, label)

    @admin.display(description="Circuit Breaker")
    def circuit_status(self, obj):
        if obj.is_circuit_open:
            return format_html('<span style="color: red;">⚠️ Aberto ({} falhas)</span>', obj.consecutive_failures)
        return format_html('<span style="color: green;">✓ Fechado</span>')


@admin.register(ERPSyncLog)
class ERPSyncLogAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "direction", "status_badge", "connection", "duration_ms", "created_at")
    list_filter = ("status", "entity_type", "direction", "connection")
    search_fields = ("entity_id", "erp_entity_id", "idempotency_key", "correlation_id")
    readonly_fields = ("request_payload", "response_payload", "created_at", "started_at", "completed_at")
    date_hierarchy = "created_at"

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {"success": "green", "failed": "red", "pending": "orange", "cancelled": "gray"}
        color = colors.get(obj.status, "gray")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_status_display())
