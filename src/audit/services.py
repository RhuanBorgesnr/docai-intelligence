"""Helper functions for writing audit logs."""
from __future__ import annotations

from typing import Any

from audit.models import AuditLog


def write_audit_log(
    *,
    action: str,
    case_id: int | None = None,
    actor_type: str = "system",
    actor_id: str = "",
    trace_id: str = "",
    correlation_id: str = "",
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Persist a new append-only audit event."""
    return AuditLog.objects.create(
        case_id=case_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        trace_id=trace_id,
        correlation_id=correlation_id,
        details=details or {},
    )
