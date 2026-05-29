"""
Tenant constants and helpers (Sprint 4 / B7 — Governance Foundation).

The DocAI platform is multi-tenant. Sprint 4 introduces a clear separation
between the **internal tenant** (the company that sells and operates DocAI —
where Jarvis/OpenClaw runs commercial, executive and growth workflows) and
**customer tenants** (paying clients of the DocAI SaaS).

All commercial, executive and growth records (leads, opportunities, internal
KPIs, executive briefings, etc.) MUST be created under ``INTERNAL_TENANT_ID``.

Customer-facing data (documents, contracts, indicators) keeps using the
existing per-customer ``tenant_id``.
"""
from __future__ import annotations

#: Tenant identifier reserved for the company that operates DocAI.
#: Used for all internal commercial / executive / growth workflows.
INTERNAL_TENANT_ID = "docai_internal"

#: Default tenant id kept for backwards compatibility with Sprint 1–3.
DEFAULT_TENANT_ID = "default"


def is_internal_tenant(tenant_id: str | None) -> bool:
    """Return True if ``tenant_id`` belongs to the internal operations tenant."""
    return (tenant_id or "").strip() == INTERNAL_TENANT_ID


def assert_internal_tenant(tenant_id: str | None) -> str:
    """
    Validate that an action belongs to the internal tenant.

    Used to guard internal-only operations (commercial pipeline, executive
    alerts, growth campaigns) against accidentally leaking into customer
    tenants. Returns the canonical tenant id on success.
    """
    if not is_internal_tenant(tenant_id):
        raise PermissionError(
            f"Operation reserved for internal tenant '{INTERNAL_TENANT_ID}', "
            f"got tenant_id={tenant_id!r}"
        )
    return INTERNAL_TENANT_ID


def resolve_tenant_id(tenant_id: str | None, *, default: str = DEFAULT_TENANT_ID) -> str:
    """Normalise an incoming tenant id, falling back to ``default`` when blank."""
    value = (tenant_id or "").strip()
    return value or default
