"""URL routes for the approvals API (Sprint 4 / Phase 4A)."""
from django.urls import path

from approvals import views

app_name = "approvals"

urlpatterns = [
    path("", views.ApprovalListView.as_view(), name="approval-list"),
    path("count/", views.ApprovalCountView.as_view(), name="approval-count"),
    path("<str:approval_id>/", views.ApprovalDetailView.as_view(), name="approval-detail"),
    path("<str:approval_id>/decide/", views.ApprovalDecideView.as_view(), name="approval-decide"),
]
