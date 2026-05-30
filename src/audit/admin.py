"""
Admin — Trilha de Auditoria (somente leitura).
"""
from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "acao", "tipo_ator", "actor_id", "case_ref", "created_at")
    list_filter = ("action", "actor_type")
    search_fields = ("action", "actor_id", "trace_id", "correlation_id", "case__title")
    readonly_fields = ("case", "action", "actor_type", "actor_id", "trace_id", "correlation_id", "details", "created_at")
    raw_id_fields = ("case",)
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Ação")
    def acao(self, obj):
        return obj.action

    @admin.display(description="Tipo Ator")
    def tipo_ator(self, obj):
        return obj.actor_type

    @admin.display(description="Case")
    def case_ref(self, obj):
        return obj.case.title if obj.case else "—"
