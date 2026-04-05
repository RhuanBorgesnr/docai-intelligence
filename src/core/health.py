"""Health check views for monitoring."""
from django.db import connection
from django.http import JsonResponse


def health_check(request):
    """Basic health check endpoint for load balancers and monitoring."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_status = "ok"
    except Exception:
        db_status = "error"

    status = "ok" if db_status == "ok" else "degraded"

    return JsonResponse({
        "status": status,
        "database": db_status,
    }, status=200 if status == "ok" else 503)
