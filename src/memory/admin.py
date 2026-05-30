"""
Admin — Memória Contextual (Snapshots).
"""
from django.contrib import admin

from .models import MemorySnapshot


@admin.register(MemorySnapshot)
class MemorySnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "case", "state", "resumo_curto", "created_at")
    list_filter = ("state",)
    search_fields = ("summary", "case__title")
    readonly_fields = ("facts", "open_questions", "pending_approvals", "snapshot_data", "created_at")
    raw_id_fields = ("case",)
    date_hierarchy = "created_at"

    @admin.display(description="Resumo")
    def resumo_curto(self, obj):
        return (obj.summary[:80] + "...") if obj.summary and len(obj.summary) > 80 else obj.summary or "—"
