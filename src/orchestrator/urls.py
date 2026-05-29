"""URL routes for orchestrator APIs."""
from django.urls import path

from orchestrator import views
from orchestrator.daily_ops import (
    AgentPerformanceView,
    CostSummaryView,
    DailyOpsView,
    ExecutionFeedbackView,
    SystemStatusView,
)

app_name = "orchestrator"

urlpatterns = [
    path("events/", views.EventIngestionView.as_view(), name="event-ingestion"),
    path("cases/", views.CaseListView.as_view(), name="case-list"),
    path("cases/<int:pk>/", views.CaseDetailView.as_view(), name="case-detail"),
    path("cases/<int:case_id>/events/", views.CaseEventListView.as_view(), name="case-events"),
    path("cases/<int:case_id>/audit/", views.CaseAuditLogListView.as_view(), name="case-audit"),

    # Operational Dashboard
    path("dashboard/", views.OperationalDashboardView.as_view(), name="dashboard"),
    path("dashboard/pipeline/", views.CasePipelineView.as_view(), name="dashboard-pipeline"),
    path("dashboard/throughput/", views.CaseThroughputView.as_view(), name="dashboard-throughput"),
    path("dashboard/approvals/", views.ApprovalSummaryView.as_view(), name="dashboard-approvals"),
    path("dashboard/notifications/", views.NotificationMetricsView.as_view(), name="dashboard-notifications"),
    path("dashboard/health/", views.SystemHealthView.as_view(), name="dashboard-health"),
    path("dashboard/agents/", views.AgentStatusView.as_view(), name="dashboard-agents"),

    # Jarvis Executive
    path("jarvis/briefing/", views.JarvisBriefingView.as_view(), name="jarvis-briefing"),
    path("jarvis/ask/", views.JarvisAskView.as_view(), name="jarvis-ask"),

    # Daily Operations (Operational Phase)
    path("ops/daily/", DailyOpsView.as_view(), name="daily-ops"),
    path("ops/costs/", CostSummaryView.as_view(), name="cost-summary"),
    path("ops/agents/<str:agent_type>/performance/", AgentPerformanceView.as_view(), name="agent-performance"),
    path("ops/executions/<str:execution_id>/feedback/", ExecutionFeedbackView.as_view(), name="execution-feedback"),
    path("ops/status/", SystemStatusView.as_view(), name="system-status"),
]
