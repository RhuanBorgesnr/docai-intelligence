"""
Admin — Busca Semântica (Embeddings de Cases).
"""
from django.contrib import admin

from .models import CaseEmbedding


@admin.register(CaseEmbedding)
class CaseEmbeddingAdmin(admin.ModelAdmin):
    list_display = ("case", "content_hash_short", "indexed_at")
    search_fields = ("case__title", "content_hash")
    readonly_fields = ("embedding", "content_hash", "indexed_at")
    raw_id_fields = ("case",)

    @admin.display(description="Hash")
    def content_hash_short(self, obj):
        return obj.content_hash[:16] + "..." if obj.content_hash else "—"
