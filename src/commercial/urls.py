"""URL routes for commercial / SDR / pipeline APIs (Sprint 4)."""
from __future__ import annotations

from django.urls import path

from commercial import views

app_name = "commercial"

urlpatterns = [
    # Ingestion
    path("leads/", views.LeadListView.as_view(), name="lead-list"),
    path("leads/ingest/", views.LeadIngestionView.as_view(), name="lead-ingest"),
    path("leads/webhook/<str:source>/", views.LeadWebhookView.as_view(), name="lead-webhook"),

    # Lead operations
    path("leads/hot/", views.HotLeadsView.as_view(), name="lead-hot"),
    path("leads/<str:lead_id>/", views.LeadDetailView.as_view(), name="lead-detail"),
    path("leads/<str:lead_id>/qualify/", views.LeadQualifyView.as_view(), name="lead-qualify"),
    path("leads/<str:lead_id>/followup/", views.LeadFollowupView.as_view(), name="lead-followup"),
    path("leads/<str:lead_id>/docai-demo/", views.DocAIDemoView.as_view(), name="lead-docai-demo"),
    path("leads/<str:lead_id>/documents/", views.LeadDocumentUploadView.as_view(), name="lead-documents"),
    path("leads/<str:lead_id>/documents/list/", views.LeadDocumentsListView.as_view(), name="lead-documents-list"),
    path("leads/<str:lead_id>/insights/", views.LeadInsightsView.as_view(), name="lead-insights"),
    path("leads/<str:lead_id>/timeline/", views.LeadTimelineView.as_view(), name="lead-timeline"),
    path("leads/<str:lead_id>/schedule-demo/", views.ScheduleDemoView.as_view(), name="lead-schedule-demo"),

    # Pipeline / opportunities
    path("pipeline/", views.CommercialPipelineSummaryView.as_view(), name="pipeline"),
    path("opportunities/", views.OpportunityListView.as_view(), name="opportunity-list"),
    path(
        "opportunities/<str:opportunity_id>/",
        views.OpportunityDetailView.as_view(),
        name="opportunity-detail",
    ),
    path(
        "opportunities/<str:opportunity_id>/stage/",
        views.OpportunityStageView.as_view(),
        name="opportunity-stage",
    ),

    # Follow-ups
    path("followups/", views.FollowUpDraftListView.as_view(), name="followup-list"),

    # Agent Team (Phase 3)
    path("agents/team/", views.AgentTeamView.as_view(), name="agent-team"),
    path("agents/<str:agent_type>/", views.AgentDetailView.as_view(), name="agent-detail"),
    path(
        "agents/<str:agent_type>/routine/<str:routine_name>/",
        views.AgentRunRoutineView.as_view(),
        name="agent-run-routine",
    ),
]
