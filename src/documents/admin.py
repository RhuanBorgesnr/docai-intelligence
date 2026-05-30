"""
Admin — Documentos e análises.
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import ContractClause, Document, DocumentChunk, ExpirationNotification, FinancialIndicator


class DocumentChunkInline(admin.TabularInline):
    model = DocumentChunk
    extra = 0
    readonly_fields = ("content_preview", "chunk_index", "token_count", "created_at")
    fields = ("chunk_index", "content_preview", "token_count", "created_at")
    can_delete = False
    show_change_link = True
    max_num = 20

    @admin.display(description="Conteúdo")
    def content_preview(self, obj):
        return (obj.content[:100] + "...") if obj.content and len(obj.content) > 100 else obj.content or "—"


class FinancialIndicatorInline(admin.TabularInline):
    model = FinancialIndicator
    extra = 0
    readonly_fields = ("indicator_type", "value", "period", "extracted_at")
    can_delete = False


class ContractClauseInline(admin.TabularInline):
    model = ContractClause
    extra = 0
    readonly_fields = ("clause_type", "title", "risk_level", "extracted_at")
    fields = ("clause_type", "title", "risk_level", "extracted_at")
    can_delete = False
    show_change_link = True


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "titulo", "tipo_doc", "status_badge", "empresa", "total_tokens", "created_at")
    list_filter = ("processing_status", "document_type", "company")
    search_fields = ("title", "file", "company__name")
    readonly_fields = ("extracted_text", "extracted_metadata", "total_tokens", "created_at")
    raw_id_fields = ("company",)
    inlines = [DocumentChunkInline, FinancialIndicatorInline, ContractClauseInline]
    date_hierarchy = "created_at"

    @admin.display(description="Título")
    def titulo(self, obj):
        return obj.title or (obj.file.name.split("/")[-1][:40] if obj.file else "—")

    @admin.display(description="Tipo")
    def tipo_doc(self, obj):
        return obj.get_document_type_display()

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {"completed": "green", "processing": "blue", "pending": "orange", "failed": "red"}
        color = colors.get(obj.processing_status, "gray")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_processing_status_display())

    @admin.display(description="Empresa")
    def empresa(self, obj):
        return obj.company.name if obj.company else "—"


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "chunk_index", "token_count", "content_preview", "created_at")
    list_filter = ("document__document_type",)
    search_fields = ("content", "document__title")
    readonly_fields = ("created_at",)

    @admin.display(description="Conteúdo")
    def content_preview(self, obj):
        return (obj.content[:80] + "...") if obj.content and len(obj.content) > 80 else obj.content or "—"


@admin.register(FinancialIndicator)
class FinancialIndicatorAdmin(admin.ModelAdmin):
    list_display = ("document", "tipo_indicador", "value", "period", "extracted_at")
    list_filter = ("indicator_type",)
    search_fields = ("document__title",)
    raw_id_fields = ("document",)

    @admin.display(description="Indicador")
    def tipo_indicador(self, obj):
        return obj.get_indicator_type_display()


@admin.register(ContractClause)
class ContractClauseAdmin(admin.ModelAdmin):
    list_display = ("document", "tipo_clausula", "title", "nivel_risco", "extracted_at")
    list_filter = ("clause_type", "risk_level")
    search_fields = ("title", "content", "document__title")
    raw_id_fields = ("document",)

    @admin.display(description="Tipo")
    def tipo_clausula(self, obj):
        return obj.get_clause_type_display()

    @admin.display(description="Risco")
    def nivel_risco(self, obj):
        colors = {"low": "green", "medium": "orange", "high": "red", "critical": "darkred"}
        color = colors.get(obj.risk_level, "gray")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_risk_level_display())


@admin.register(ExpirationNotification)
class ExpirationNotificationAdmin(admin.ModelAdmin):
    list_display = ("document", "notification_type", "sent_to", "sent_at")
    list_filter = ("notification_type",)
    search_fields = ("sent_to", "document__title")
    raw_id_fields = ("document",)
