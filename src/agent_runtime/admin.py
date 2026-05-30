"""
Admin — Runtime de Agentes (Comandos, Respostas, Prompts, Execuções).
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import AgentCommand, AgentExecution, AgentResponse, PromptDefinition


@admin.register(AgentCommand)
class AgentCommandAdmin(admin.ModelAdmin):
    list_display = ("command_id_short", "tipo", "agente_origem", "agente_destino", "status_badge", "prioridade", "created_at")
    list_filter = ("status", "priority", "source_agent", "target_agent", "command_type")
    search_fields = ("command_id", "correlation_id", "trace_id", "case__title")
    readonly_fields = (
        "command_id", "input_payload", "expected_output_schema",
        "created_at", "updated_at", "started_at", "completed_at", "last_error"
    )
    raw_id_fields = ("case",)
    date_hierarchy = "created_at"

    @admin.display(description="Comando")
    def command_id_short(self, obj):
        return obj.command_id[:12] + "..."

    @admin.display(description="Tipo")
    def tipo(self, obj):
        return obj.command_type

    @admin.display(description="Origem")
    def agente_origem(self, obj):
        return obj.source_agent

    @admin.display(description="Destino")
    def agente_destino(self, obj):
        return obj.target_agent

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {"pending": "orange", "claimed": "blue", "running": "blue", "completed": "green", "failed": "red", "timeout": "red"}
        color = colors.get(obj.status, "gray")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_status_display())

    @admin.display(description="Prioridade")
    def prioridade(self, obj):
        return obj.get_priority_display()


@admin.register(AgentResponse)
class AgentResponseAdmin(admin.ModelAdmin):
    list_display = ("response_id_short", "agent_id", "status_badge", "model_name", "provider", "created_at")
    list_filter = ("status", "agent_id", "provider", "model_name")
    search_fields = ("response_id", "agent_id", "trace_id")
    readonly_fields = ("response_id", "output_payload", "quality", "created_at")
    raw_id_fields = ("command",)

    @admin.display(description="Resposta")
    def response_id_short(self, obj):
        return obj.response_id[:12] + "..."

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {"success": "green", "error": "red", "partial": "orange"}
        color = colors.get(obj.status, "gray")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_status_display())


@admin.register(PromptDefinition)
class PromptDefinitionAdmin(admin.ModelAdmin):
    list_display = ("agent_type", "version", "status_badge", "tenant_id", "descricao_curta", "activated_at")
    list_filter = ("status", "agent_type", "tenant_id")
    search_fields = ("agent_type", "description", "content")
    readonly_fields = ("content_hash", "created_at", "updated_at", "activated_at")
    ordering = ("agent_type", "-version")

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {"active": "green", "draft": "orange", "deprecated": "gray", "canary": "blue"}
        color = colors.get(obj.status, "gray")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_status_display())

    @admin.display(description="Descrição")
    def descricao_curta(self, obj):
        return (obj.description[:60] + "...") if obj.description and len(obj.description) > 60 else obj.description or "—"


@admin.register(AgentExecution)
class AgentExecutionAdmin(admin.ModelAdmin):
    list_display = ("execution_id_short", "agent_type", "provider", "model_name", "tokens_total", "custo", "latencia", "status_badge", "created_at")
    list_filter = ("agent_type", "provider", "model_name", "status", "cache_hit")
    search_fields = ("execution_id", "correlation_id", "lead_id", "tenant_id")
    readonly_fields = ("execution_id", "created_at", "output_summary", "error_message")
    date_hierarchy = "created_at"

    @admin.display(description="Execução")
    def execution_id_short(self, obj):
        return obj.execution_id[:12] + "..."

    @admin.display(description="Tokens")
    def tokens_total(self, obj):
        return obj.total_tokens or 0

    @admin.display(description="Custo")
    def custo(self, obj):
        return f"${obj.estimated_cost_usd:.4f}" if obj.estimated_cost_usd else "—"

    @admin.display(description="Latência")
    def latencia(self, obj):
        return f"{obj.latency_ms}ms" if obj.latency_ms else "—"

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {"success": "green", "error": "red", "timeout": "orange"}
        color = colors.get(obj.status, "gray")
        return format_html('<span style="color: {};">{}</span>', color, obj.status)
