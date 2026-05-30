from django.contrib import admin
from django.utils.html import format_html

from .models import FollowUpDraft, Lead, LeadScoreEvent, Opportunity


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("lead_id", "company_name", "contact_email", "status_badge", "score_badge", "source", "created_at")
    list_filter = ("status", "source", "tenant_id", "country")
    search_fields = ("lead_id", "company_name", "contact_email", "contact_name")
    readonly_fields = ("lead_id", "created_at", "updated_at", "last_event_at", "icp_fit", "payload")
    date_hierarchy = "created_at"
    raw_id_fields = ("case",)

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {"new": "blue", "qualified": "green", "hot": "red", "disqualified": "gray", "converted": "purple"}
        color = colors.get(obj.status, "gray")
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display())

    @admin.display(description="Score")
    def score_badge(self, obj):
        if obj.score >= 80:
            color = "green"
        elif obj.score >= 50:
            color = "orange"
        else:
            color = "gray"
        return format_html('<span style="color: {};">{}</span>', color, obj.score)


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("opportunity_id", "lead", "estagio", "valor_estimado", "probabilidade", "created_at")
    list_filter = ("stage", "tenant_id")
    search_fields = ("opportunity_id", "lead__company_name", "lead__lead_id")
    readonly_fields = ("opportunity_id", "created_at", "updated_at", "closed_at")
    raw_id_fields = ("lead", "case")

    @admin.display(description="Estágio")
    def estagio(self, obj):
        return obj.get_stage_display()

    @admin.display(description="Valor Estimado")
    def valor_estimado(self, obj):
        return f"R$ {obj.estimated_value:,.2f}" if obj.estimated_value else "—"

    @admin.display(description="Probabilidade")
    def probabilidade(self, obj):
        return f"{int(obj.win_probability * 100)}%" if obj.win_probability else "—"


@admin.register(LeadScoreEvent)
class LeadScoreEventAdmin(admin.ModelAdmin):
    list_display = ("lead", "score_before", "score_after", "variacao", "reason", "created_at")
    list_filter = ("reason",)
    search_fields = ("lead__lead_id", "lead__company_name")
    readonly_fields = ("created_at",)

    @admin.display(description="Variação")
    def variacao(self, obj):
        diff = obj.score_after - obj.score_before
        color = "green" if diff > 0 else "red"
        return format_html('<span style="color: {};">{:+d}</span>', color, diff)


@admin.register(FollowUpDraft)
class FollowUpDraftAdmin(admin.ModelAdmin):
    list_display = ("draft_id", "lead", "channel", "status_badge", "created_by_agent", "created_at")
    list_filter = ("status", "channel", "tenant_id", "created_by_agent")
    search_fields = ("draft_id", "lead__lead_id", "subject")
    readonly_fields = ("draft_id", "created_at", "updated_at", "sent_at")
    raw_id_fields = ("lead", "opportunity")

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {"draft": "gray", "pending_approval": "orange", "approved": "blue", "sent": "green", "rejected": "red"}
        color = colors.get(obj.status, "gray")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_status_display())
