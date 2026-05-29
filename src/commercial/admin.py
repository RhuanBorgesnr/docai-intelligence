from django.contrib import admin

from commercial.models import FollowUpDraft, Lead, LeadScoreEvent, Opportunity


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("lead_id", "company_name", "contact_email", "status", "score", "source", "created_at")
    list_filter = ("status", "source", "tenant_id", "country")
    search_fields = ("lead_id", "company_name", "contact_email", "contact_name")
    readonly_fields = ("lead_id", "created_at", "updated_at")


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("opportunity_id", "lead", "stage", "estimated_value", "win_probability", "created_at")
    list_filter = ("stage", "tenant_id")
    search_fields = ("opportunity_id", "lead__company_name", "lead__lead_id")


@admin.register(LeadScoreEvent)
class LeadScoreEventAdmin(admin.ModelAdmin):
    list_display = ("lead", "score_before", "score_after", "reason", "created_at")
    list_filter = ("reason",)


@admin.register(FollowUpDraft)
class FollowUpDraftAdmin(admin.ModelAdmin):
    list_display = ("draft_id", "lead", "channel", "status", "created_by_agent", "created_at")
    list_filter = ("status", "channel", "tenant_id")
    search_fields = ("draft_id", "lead__lead_id", "subject")
