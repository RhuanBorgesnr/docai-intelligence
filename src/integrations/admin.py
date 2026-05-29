from django.contrib import admin

from .models import ERPConnection, ERPFieldMapping, ERPSyncLog


class ERPFieldMappingInline(admin.TabularInline):
    model = ERPFieldMapping
    extra = 0


@admin.register(ERPConnection)
class ERPConnectionAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "tenant_id", "is_active", "is_circuit_open", "last_sync_at")
    list_filter = ("provider", "is_active", "is_circuit_open")
    search_fields = ("name", "tenant_id")
    inlines = [ERPFieldMappingInline]


@admin.register(ERPSyncLog)
class ERPSyncLogAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "direction", "status", "connection", "created_at")
    list_filter = ("status", "entity_type", "direction")
    search_fields = ("entity_id", "erp_entity_id", "idempotency_key")
    readonly_fields = ("request_payload", "response_payload")
