"""
Admin — Aprovações (Human-in-the-Loop).
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import Approval


@admin.register(Approval)
class ApprovalAdmin(admin.ModelAdmin):
    list_display = ("approval_id_short", "tipo", "status_badge", "agente_solicitante", "tenant_id", "requested_at", "deadline_at", "decided_at")
    list_filter = ("status", "approval_type", "requested_by_agent", "tenant_id")
    search_fields = ("approval_id", "summary", "correlation_id", "trace_id", "case__title")
    readonly_fields = (
        "approval_id", "approvers", "escalated_to", "payload",
        "policy_snapshot", "approval_fields", "requested_at", "decided_at"
    )
    raw_id_fields = ("case", "decided_by")
    date_hierarchy = "requested_at"
    fieldsets = (
        ("Identificação", {
            "fields": ("approval_id", "case", "approval_type", "summary")
        }),
        ("Status", {
            "fields": ("status", "decided_by", "decision_comment", "requested_at", "deadline_at", "decided_at")
        }),
        ("Solicitação", {
            "fields": ("requested_by_agent", "tenant_id", "correlation_id", "trace_id")
        }),
        ("Dados", {
            "fields": ("payload", "approval_fields", "policy_snapshot"),
            "classes": ("collapse",),
        }),
        ("Escalação", {
            "fields": ("escalation_at", "escalated_to", "escalation_reason"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="ID")
    def approval_id_short(self, obj):
        return obj.approval_id[:12] + "..."

    @admin.display(description="Tipo")
    def tipo(self, obj):
        return obj.approval_type

    @admin.display(description="Solicitante")
    def agente_solicitante(self, obj):
        return obj.requested_by_agent

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {"pending": "orange", "approved": "green", "rejected": "red", "escalated": "purple", "expired": "gray"}
        color = colors.get(obj.status, "gray")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())
