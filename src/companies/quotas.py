"""
Quota enforcement for DRF views.

Usage in views:
    from companies.quotas import QuotaCheckMixin

    class DocumentUploadView(QuotaCheckMixin, CreateAPIView):
        quota_resource = 'document'
        ...
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework import status


class QuotaCheckMixin:
    """
    DRF view mixin that checks quota before processing request.

    Set `quota_resource` on the view class:
    - 'document' — checks document upload limit
    - 'ai_query' — checks AI query limit
    - 'user' — checks user invitation limit
    """
    quota_resource: str | None = None

    def check_quota(self, request) -> tuple[bool, str]:
        """Check if tenant has quota for the requested resource."""
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return True, "OK"  # No tenant = no quota enforcement (staff, etc.)

        if not self.quota_resource:
            return True, "OK"

        return tenant.check_quota(self.quota_resource)

    def create(self, request, *args, **kwargs):
        allowed, message = self.check_quota(request)
        if not allowed:
            return Response(
                {"error": message, "code": "quota_exceeded"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        """Override to auto-assign tenant company."""
        tenant = getattr(self.request, 'tenant', None)
        if tenant and hasattr(serializer.Meta.model, 'company'):
            serializer.save(company=tenant)
        else:
            serializer.save()


class AIQuotaCheckMixin:
    """
    Mixin for AI-related views that increments usage counter.
    """

    def check_and_increment_ai_quota(self, request) -> tuple[bool, str]:
        """Check AI quota and increment if allowed."""
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return True, "OK"

        allowed, message = tenant.check_quota('ai_query')
        if not allowed:
            return False, message

        tenant.increment_ai_usage()
        return True, "OK"
