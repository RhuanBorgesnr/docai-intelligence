"""URL configuration for ERP Integrations."""
from django.urls import path

from . import views

app_name = "integrations"

urlpatterns = [
    # Connections CRUD
    path("connections/", views.ERPConnectionListCreateView.as_view(), name="connection-list"),
    path("connections/<uuid:pk>/", views.ERPConnectionDetailView.as_view(), name="connection-detail"),
    path("connections/test/", views.TestConnectionView.as_view(), name="connection-test"),

    # Sync operations
    path("sync/", views.SyncDocumentView.as_view(), name="sync-document"),
    path("sync/approve/", views.ApproveSyncView.as_view(), name="sync-approve"),
    path("sync/logs/", views.ERPSyncLogListView.as_view(), name="sync-logs"),
    path("sync/stats/", views.ERPSyncStatsView.as_view(), name="sync-stats"),

    # Field mappings
    path("mappings/", views.ERPFieldMappingListCreateView.as_view(), name="field-mappings"),
]
