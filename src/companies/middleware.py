"""
Tenant isolation middleware — ensures every request is scoped to the user's company.

Adds `request.tenant` (Company instance or None) for use in views.
Enforces subscription status on protected endpoints.
"""
from __future__ import annotations

from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin


# Paths that don't require tenant context
EXEMPT_PATHS = (
    '/api/auth/',
    '/api/accounts/register/',
    '/api/accounts/password-reset/',
    '/api/health/',
    '/api/schema/',
    '/api/docs/',
    '/api/redoc/',
    '/admin/',
    '/ws/',
)

# Paths that require active subscription (not just auth)
SUBSCRIPTION_REQUIRED_PATHS = (
    '/api/documents/',
    '/api/search/',
    '/api/chat/',
)


class TenantMiddleware(MiddlewareMixin):
    """
    Attaches tenant (Company) to request and enforces subscription checks.

    After auth middleware runs, this resolves the user's company and:
    1. Sets request.tenant = Company or None
    2. For protected paths, rejects if no tenant or subscription inactive
    """

    def process_request(self, request):
        request.tenant = None

        # Skip exempt paths
        path = request.path
        if any(path.startswith(p) for p in EXEMPT_PATHS):
            return None

        # Anonymous users handled by DRF auth
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None

        # Staff users bypass tenant checks (ops dashboard)
        if user.is_staff:
            return None

        # Resolve tenant from user profile
        profile = getattr(user, 'userprofile', None)
        if profile and profile.company:
            request.tenant = profile.company
        else:
            # User has no company — only block subscription-required paths
            if any(path.startswith(p) for p in SUBSCRIPTION_REQUIRED_PATHS):
                return JsonResponse(
                    {"error": "Nenhuma empresa vinculada. Complete o onboarding."},
                    status=403,
                )
            return None

        # Check subscription for protected paths
        if any(path.startswith(p) for p in SUBSCRIPTION_REQUIRED_PATHS):
            company = request.tenant
            if not company.is_subscription_active:
                return JsonResponse(
                    {"error": "Assinatura inativa. Renove seu plano para continuar."},
                    status=402,
                )

        return None
