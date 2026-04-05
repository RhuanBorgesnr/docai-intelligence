"""
Document API URL configuration.
"""
from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.DocumentListCreateView.as_view(), name="list-create"),
    path("stats/", views.DocumentStatsView.as_view(), name="stats"),
    path("expiring/", views.ExpiringDocumentsView.as_view(), name="expiring"),
    path("financial/", views.FinancialDashboardView.as_view(), name="financial-dashboard"),
    path("financial/history/", views.IndicatorHistoryView.as_view(), name="indicator-history"),
    path("financial/history/all/", views.AllIndicatorsHistoryView.as_view(), name="all-indicators-history"),
    path("financial/compare/", views.ComparePeriodsView.as_view(), name="compare-periods"),
    path("financial/comparable/", views.ComparableDocumentsView.as_view(), name="comparable-documents"),
    path("financial/report/", views.DownloadComparisonReportView.as_view(), name="comparison-report"),
    path("contracts/", views.ContractsWithClausesView.as_view(), name="contracts-with-clauses"),
    path("<int:pk>/", views.DocumentDetailView.as_view(), name="detail"),
    path("<int:pk>/indicators/", views.DocumentIndicatorsView.as_view(), name="indicators"),
    path("<int:pk>/extract-indicators/", views.ExtractIndicatorsView.as_view(), name="extract-indicators"),
    path("<int:pk>/report/", views.DownloadReportView.as_view(), name="document-report"),
    path("<int:pk>/clauses/", views.DocumentClausesView.as_view(), name="clauses"),
    path("<int:pk>/extract-clauses/", views.ExtractClausesView.as_view(), name="extract-clauses"),
]
