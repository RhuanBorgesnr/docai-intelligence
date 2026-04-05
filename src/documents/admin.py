"""
Admin configuration for documents app.
"""
from django.contrib import admin

from .models import Document, DocumentChunk


class DocumentChunkInline(admin.TabularInline):
    """Inline admin for document chunks."""

    model = DocumentChunk
    extra = 0
    readonly_fields = ("content", "chunk_index", "token_count", "created_at")
    can_delete = True
    show_change_link = True
    max_num = 20


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Admin for Document model."""

    list_display = ("id", "file_preview", "processing_status", "total_tokens", "created_at")
    list_filter = ("processing_status",)
    search_fields = ("file__icontains",)
    readonly_fields = ("extracted_text", "total_tokens", "created_at")
    inlines = [DocumentChunkInline]

    def file_preview(self, obj):
        """Return truncated file name."""
        return obj.file.name.split("/")[-1][:50] if obj.file else "-"

    file_preview.short_description = "File"


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    """Admin for DocumentChunk model."""

    list_display = ("id", "document", "chunk_index", "token_count", "content_preview", "created_at")
    list_filter = ("document",)
    search_fields = ("content",)

    def content_preview(self, obj):
        """Return truncated content."""
        return (obj.content[:80] + "...") if obj.content and len(obj.content) > 80 else obj.content or "-"

    content_preview.short_description = "Content"
