"""
Jarvis Tools — callable functions available to the executive agent.

Each tool is a plain function that takes structured input and returns
a dict result.  The ``TOOL_REGISTRY`` maps tool names to callables so
the Jarvis agent can invoke them by name.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# ── get_case_summary ─────────────────────────────────────────────────────────

def get_case_summary(case_id: int) -> dict:
    """
    Return a compact summary of a Case: state, priority, recent events,
    pending approvals and notifications.
    """
    from approvals.models import Approval
    from notifications.models import Notification
    from orchestrator.models import Case, CaseEvent

    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return {"error": f"Case {case_id} not found"}

    events = list(
        CaseEvent.objects.filter(case=case)
        .order_by("-created_at")[:5]
        .values("event_type", "source", "created_at")
    )
    for e in events:
        e["created_at"] = e["created_at"].isoformat()

    pending_approvals = list(
        Approval.objects.filter(case=case, status="pending")
        .values("approval_id", "approval_type", "summary")
    )

    pending_notifications = (
        Notification.objects.filter(case=case, status="pending").count()
    )

    return {
        "case_id": case.id,
        "external_ref": case.external_ref,
        "title": case.title,
        "state": case.state,
        "workflow_status": case.workflow_status,
        "priority": case.priority,
        "tenant_id": case.tenant_id,
        "created_at": case.created_at.isoformat(),
        "recent_events": events,
        "pending_approvals": pending_approvals,
        "pending_notifications": pending_notifications,
    }


# ── list_pending_approvals ───────────────────────────────────────────────────

def list_pending_approvals(tenant_id: Optional[str] = None, limit: int = 10) -> dict:
    """Return pending approvals, flagging any overdue."""
    from approvals.models import Approval

    qs = Approval.objects.filter(status="pending").order_by("deadline_at")
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)

    approvals = []
    now = timezone.now()
    for apv in qs[:limit]:
        overdue = bool(apv.deadline_at and apv.deadline_at < now)
        approvals.append({
            "approval_id": apv.approval_id,
            "case_id": apv.case_id,
            "approval_type": apv.approval_type,
            "summary": apv.summary[:200],
            "requested_by": apv.requested_by_agent,
            "deadline_at": apv.deadline_at.isoformat() if apv.deadline_at else None,
            "overdue": overdue,
        })

    return {"count": len(approvals), "approvals": approvals}


# ── view_metrics ─────────────────────────────────────────────────────────────

def view_metrics(tenant_id: Optional[str] = None) -> dict:
    """Return operational KPIs for the briefing."""
    from orchestrator.dashboard import (
        get_approval_summary,
        get_case_pipeline,
        get_case_throughput,
        get_notification_metrics,
        get_system_health,
    )

    return {
        "pipeline": get_case_pipeline(tenant_id),
        "throughput": get_case_throughput(tenant_id=tenant_id),
        "approvals": get_approval_summary(tenant_id),
        "notifications": get_notification_metrics(tenant_id),
        "health": get_system_health(),
    }


# ── send_notification ────────────────────────────────────────────────────────

def send_notification(
    case_id: int,
    channel: str = "email",
    recipient: str = "",
    message: str = "",
    subject: str = "",
) -> dict:
    """Enqueue a notification for a case."""
    import uuid

    from notifications.models import Notification
    from orchestrator.models import Case

    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return {"error": f"Case {case_id} not found"}

    ntf = Notification.objects.create(
        notification_id=f"jarvis-{uuid.uuid4().hex[:12]}",
        case=case,
        tenant_id=case.tenant_id,
        channel=channel,
        recipient=recipient,
        subject=subject,
        message=message,
        status="pending",
    )

    return {
        "notification_id": ntf.notification_id,
        "status": "queued",
        "channel": channel,
    }


# ── route_to_agent ───────────────────────────────────────────────────────────

def route_to_agent(case_id: int, target_agent: str, instruction: str = "") -> dict:
    """
    Dispatch a command to a specialist agent via the inter-agent bus.

    This is the primary mechanism Jarvis uses to delegate work.
    """
    import uuid

    from orchestrator.models import Case

    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return {"error": f"Case {case_id} not found"}

    from agent_runtime.inter_agent_bus import InterAgentBus

    bus = InterAgentBus()
    cmd_id = bus.send_command(
        source="jarvis",
        target=target_agent,
        command_type=f"process_case",
        payload={
            "case_id": case.id,
            "external_ref": case.external_ref,
            "state": case.state,
            "instruction": instruction,
        },
        correlation_id=case.correlation_id,
        trace_id=case.trace_id,
        idempotency_key=f"jarvis-route-{case.id}-{target_agent}-{case.state}",
    )

    return {
        "command_id": cmd_id,
        "target_agent": target_agent,
        "case_id": case.id,
        "status": "dispatched",
    }


# ── find_similar_cases ───────────────────────────────────────────────────────

def find_similar_cases_tool(query: str, limit: int = 3) -> dict:
    """Semantic search for similar past cases."""
    from search.services import find_similar_cases

    results = find_similar_cases(query=query, limit=limit)
    return {"count": len(results), "cases": results}


# ══════════════════════════════════════════════════════════════════════════════
#  Tool Registry
# ══════════════════════════════════════════════════════════════════════════════

TOOL_REGISTRY: dict[str, callable] = {
    "get_case_summary": get_case_summary,
    "list_pending_approvals": list_pending_approvals,
    "view_metrics": view_metrics,
    "send_notification": send_notification,
    "route_to_agent": route_to_agent,
    "find_similar_cases": find_similar_cases_tool,
}


def execute_tool(tool_name: str, **kwargs) -> dict:
    """Look up and execute a tool by name."""
    fn = TOOL_REGISTRY.get(tool_name)
    if not fn:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return fn(**kwargs)
    except Exception as exc:
        logger.exception("Tool %s failed: %s", tool_name, exc)
        return {"error": str(exc), "tool": tool_name}
