"""
Operational Dashboard – metrics aggregation service.

Provides a consolidated view of:
- Case pipeline (by state, priority, workflow_status, throughput)
- Approval queue (pending, decided, expired, SLA)
- Notification delivery (by channel, status, failure rate)
- System health (circuit breakers, dead-letter queue)
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.db.models import Avg, Count, F, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


# ── Case Pipeline ─────────────────────────────────────────────────────────────

def get_case_pipeline(tenant_id: Optional[str] = None) -> dict:
    """
    Return case counts grouped by state, priority, and workflow_status.

    Response shape::

        {
            "total": int,
            "by_state": {"new": int, "triage": int, ...},
            "by_priority": {"low": int, ...},
            "by_workflow_status": {"running": int, ...},
            "active": int,
            "completed": int,
            "failed": int,
        }
    """
    from orchestrator.models import Case

    qs = Case.objects.all()
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)

    total = qs.count()
    by_state = dict(qs.values_list("state").annotate(c=Count("id")).values_list("state", "c"))
    by_priority = dict(qs.values_list("priority").annotate(c=Count("id")).values_list("priority", "c"))
    by_workflow = dict(
        qs.values_list("workflow_status").annotate(c=Count("id")).values_list("workflow_status", "c")
    )

    terminal_states = {"won", "lost", "closed"}
    active = sum(v for k, v in by_state.items() if k not in terminal_states and k != "failed")
    completed = sum(v for k, v in by_state.items() if k in terminal_states)
    failed = by_state.get("failed", 0)

    return {
        "total": total,
        "by_state": by_state,
        "by_priority": by_priority,
        "by_workflow_status": by_workflow,
        "active": active,
        "completed": completed,
        "failed": failed,
    }


def get_case_throughput(days: int = 30, tenant_id: Optional[str] = None) -> dict:
    """
    Return case creation / completion counts over recent *days*.

    Response shape::

        {
            "period_days": int,
            "created": int,
            "completed": int,
            "avg_resolution_hours": float | None,
        }
    """
    from orchestrator.models import Case

    since = timezone.now() - timedelta(days=days)
    qs = Case.objects.all()
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)

    created = qs.filter(created_at__gte=since).count()
    terminal = {"won", "lost", "closed"}
    completed_qs = qs.filter(state__in=terminal, updated_at__gte=since)
    completed = completed_qs.count()

    avg_hours = None
    if completed:
        avg_delta = completed_qs.aggregate(
            avg_dur=Avg(F("updated_at") - F("created_at"))
        )["avg_dur"]
        if avg_delta:
            avg_hours = round(avg_delta.total_seconds() / 3600, 1)

    return {
        "period_days": days,
        "created": created,
        "completed": completed,
        "avg_resolution_hours": avg_hours,
    }


# ── Approval Queue ───────────────────────────────────────────────────────────

def get_approval_summary(tenant_id: Optional[str] = None) -> dict:
    """
    Return approval metrics.

    Response shape::

        {
            "total": int,
            "pending": int,
            "approved": int,
            "rejected": int,
            "expired": int,
            "escalated": int,
            "by_type": {"financial": int, ...},
            "overdue": int,
        }
    """
    from approvals.models import Approval

    qs = Approval.objects.all()
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)

    total = qs.count()
    by_status = dict(qs.values_list("status").annotate(c=Count("id")).values_list("status", "c"))
    by_type = dict(
        qs.values_list("approval_type").annotate(c=Count("id")).values_list("approval_type", "c")
    )

    overdue = qs.filter(
        status="pending",
        deadline_at__lt=timezone.now(),
    ).count()

    return {
        "total": total,
        "pending": by_status.get("pending", 0),
        "approved": by_status.get("approved", 0),
        "rejected": by_status.get("rejected", 0),
        "expired": by_status.get("expired", 0),
        "escalated": by_status.get("escalated", 0),
        "by_type": by_type,
        "overdue": overdue,
    }


# ── Notification Delivery ────────────────────────────────────────────────────

def get_notification_metrics(tenant_id: Optional[str] = None) -> dict:
    """
    Return notification delivery statistics.

    Response shape::

        {
            "total": int,
            "sent": int,
            "failed": int,
            "pending": int,
            "dead_letter": int,
            "by_channel": {"email": {"total": int, "sent": int, "failed": int}, ...},
            "avg_attempts": float | None,
        }
    """
    from notifications.models import Notification

    qs = Notification.objects.all()
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)

    total = qs.count()
    by_status = dict(qs.values_list("status").annotate(c=Count("id")).values_list("status", "c"))
    dead_letter = qs.filter(is_dead=True).count()

    # Per-channel breakdown
    channel_data = (
        qs.values("channel", "status")
        .annotate(c=Count("id"))
        .order_by("channel", "status")
    )
    by_channel: dict[str, dict] = {}
    for row in channel_data:
        ch = row["channel"]
        if ch not in by_channel:
            by_channel[ch] = {"total": 0, "sent": 0, "failed": 0}
        by_channel[ch]["total"] += row["c"]
        if row["status"] == "sent":
            by_channel[ch]["sent"] += row["c"]
        elif row["status"] in ("failed", "failed_fallback"):
            by_channel[ch]["failed"] += row["c"]

    avg_attempts = qs.aggregate(avg_att=Avg("attempts"))["avg_att"]
    if avg_attempts is not None:
        avg_attempts = round(avg_attempts, 2)

    return {
        "total": total,
        "sent": by_status.get("sent", 0),
        "failed": by_status.get("failed", 0) + by_status.get("failed_fallback", 0),
        "pending": by_status.get("pending", 0),
        "dead_letter": dead_letter,
        "by_channel": by_channel,
        "avg_attempts": avg_attempts,
    }


# ── System Health ────────────────────────────────────────────────────────────

def get_system_health() -> dict:
    """
    Return operational health indicators.

    Response shape::

        {
            "circuit_breakers": [{"channel": str, "is_open": bool, ...}, ...],
            "dlq_size": int,
            "pending_notifications": int,
            "pending_approvals": int,
        }
    """
    from approvals.models import Approval
    from notifications.models import Notification, NotificationProviderHealth
    from orchestrator.models import DLQEvent

    breakers = list(
        NotificationProviderHealth.objects.values(
            "channel", "is_open", "failure_count", "success_count",
            "last_failure_at", "last_success_at",
        )
    )

    dlq_size = DLQEvent.objects.count()
    pending_notif = Notification.objects.filter(status="pending").count()
    pending_appr = Approval.objects.filter(status="pending").count()

    return {
        "circuit_breakers": breakers,
        "dlq_size": dlq_size,
        "pending_notifications": pending_notif,
        "pending_approvals": pending_appr,
    }


# ── Full Summary ─────────────────────────────────────────────────────────────

def get_operational_summary(tenant_id: Optional[str] = None) -> dict:
    """
    Return the full operational dashboard payload combining all sections.
    """
    return {
        "pipeline": get_case_pipeline(tenant_id),
        "throughput": get_case_throughput(tenant_id=tenant_id),
        "approvals": get_approval_summary(tenant_id),
        "notifications": get_notification_metrics(tenant_id),
        "health": get_system_health(),
        "generated_at": timezone.now().isoformat(),
    }


# ── Agent Status (for visual operations dashboard) ───────────────────────────

# Canonical agent topology — defines which agents exist and how they connect.
AGENT_TOPOLOGY = [
    {
        "id": "jarvis",
        "label": "Jarvis Orchestrator",
        "role": "orchestrator",
        "position": [0, 0, 0],
        "connections": ["intake", "sdr", "sales", "docai", "approval_gw", "notifications", "memory_rag"],
    },
    {
        "id": "intake",
        "label": "Intake Agent",
        "role": "agent",
        "position": [-3, 2, 0],
        "connections": ["jarvis"],
    },
    {
        "id": "sdr",
        "label": "SDR Agent",
        "role": "agent",
        "position": [-1.5, 3, 0],
        "connections": ["jarvis"],
    },
    {
        "id": "sales",
        "label": "Sales Agent",
        "role": "agent",
        "position": [1.5, 3, 0],
        "connections": ["jarvis"],
    },
    {
        "id": "docai",
        "label": "DocAI Operator",
        "role": "operator",
        "position": [3, 2, 0],
        "connections": ["jarvis"],
    },
    {
        "id": "approval_gw",
        "label": "Approval Gateway",
        "role": "gateway",
        "position": [-2, -2, 0],
        "connections": ["jarvis"],
    },
    {
        "id": "notifications",
        "label": "Notification Service",
        "role": "service",
        "position": [2, -2, 0],
        "connections": ["jarvis"],
    },
    {
        "id": "memory_rag",
        "label": "Memory / RAG",
        "role": "service",
        "position": [0, -3, 0],
        "connections": ["jarvis"],
    },
]

# Maps agent ids to the Case states they handle (for live status inference)
_AGENT_STATE_MAP = {
    "intake": {"new", "triage"},
    "sdr": {"qualified", "waiting_doc_sample"},
    "sales": {"proposal_draft_ready", "followup_scheduled"},
    "docai": {"doc_sent_to_docai", "analysis_ready"},
    "approval_gw": {"waiting_human_approval", "approved_to_send"},
}


def get_agent_status(tenant_id: Optional[str] = None) -> dict:
    """
    Build the full agent-status payload for the visual operations dashboard.

    Returns::

        {
            "agents": [{id, label, role, position, connections, status, queue_size, error_count}, ...],
            "recent_events": [{type, source, target, timestamp}, ...],
            "summary": {active_cases, pending_approvals, pending_notifications, dlq_size},
        }
    """
    from approvals.models import Approval
    from notifications.models import Notification
    from orchestrator.models import Case, CaseEvent, DLQEvent

    qs_case = Case.objects.all()
    if tenant_id:
        qs_case = qs_case.filter(tenant_id=tenant_id)

    # Count cases per state
    state_counts = dict(
        qs_case.values_list("state").annotate(c=Count("id")).values_list("state", "c")
    )

    # Count pending approvals
    appr_qs = Approval.objects.filter(status="pending")
    if tenant_id:
        appr_qs = appr_qs.filter(tenant_id=tenant_id)
    pending_approvals = appr_qs.count()

    # Count pending notifications
    notif_qs = Notification.objects.filter(status="pending")
    if tenant_id:
        notif_qs = notif_qs.filter(tenant_id=tenant_id)
    pending_notifications = notif_qs.count()

    # DLQ
    dlq_size = DLQEvent.objects.count()

    # Build agent list with live status
    agents = []
    for topo in AGENT_TOPOLOGY:
        agent_id = topo["id"]
        queue_size = 0
        error_count = 0
        agent_status = "idle"

        if agent_id == "jarvis":
            running = sum(
                v for k, v in state_counts.items()
                if k not in {"won", "lost", "closed", "failed"}
            )
            queue_size = running
            agent_status = "active" if running > 0 else "idle"
            error_count = state_counts.get("failed", 0)
        elif agent_id == "approval_gw":
            queue_size = pending_approvals
            overdue = appr_qs.filter(deadline_at__lt=timezone.now()).count()
            agent_status = "warning" if overdue > 0 else ("active" if pending_approvals > 0 else "idle")
            error_count = overdue
        elif agent_id == "notifications":
            queue_size = pending_notifications
            failed = Notification.objects.filter(
                status__in=["failed", "failed_fallback"],
            ).count()
            agent_status = "error" if failed > 0 else ("active" if pending_notifications > 0 else "idle")
            error_count = failed
        elif agent_id == "memory_rag":
            from search.models import CaseEmbedding
            indexed = CaseEmbedding.objects.count()
            queue_size = indexed
            agent_status = "active" if indexed > 0 else "idle"
        elif agent_id in _AGENT_STATE_MAP:
            states = _AGENT_STATE_MAP[agent_id]
            queue_size = sum(state_counts.get(s, 0) for s in states)
            agent_status = "active" if queue_size > 0 else "idle"
            if agent_id == "docai":
                error_count = state_counts.get("failed", 0)
                if error_count > 0:
                    agent_status = "warning"

        agents.append({
            **topo,
            "status": agent_status,
            "queue_size": queue_size,
            "error_count": error_count,
        })

    # Recent events (last 20) for animation
    recent_events_qs = CaseEvent.objects.order_by("-created_at")[:20]
    recent_events = [
        {
            "type": evt.event_type,
            "source": _event_source_agent(evt.event_type),
            "target": _event_target_agent(evt.event_type),
            "timestamp": evt.created_at.isoformat(),
        }
        for evt in recent_events_qs
    ]

    return {
        "agents": agents,
        "recent_events": recent_events,
        "summary": {
            "active_cases": sum(
                v for k, v in state_counts.items()
                if k not in {"won", "lost", "closed", "failed"}
            ),
            "pending_approvals": pending_approvals,
            "pending_notifications": pending_notifications,
            "dlq_size": dlq_size,
        },
    }


def _event_source_agent(event_type: str) -> str:
    """Infer which agent *produced* an event."""
    mapping = {
        "lead.received": "intake",
        "lead.qualified": "sdr",
        "document.sample.requested": "sdr",
        "document.sample.received": "intake",
        "docai.analysis.requested": "jarvis",
        "docai.analysis.completed": "docai",
        "proposal.draft.generated": "sales",
        "approval.required": "jarvis",
        "approval.granted": "approval_gw",
        "approval.rejected": "approval_gw",
        "workflow.transitioned": "jarvis",
        "workflow.failed": "jarvis",
    }
    return mapping.get(event_type, "jarvis")


def _event_target_agent(event_type: str) -> str:
    """Infer which agent *receives* an event."""
    mapping = {
        "lead.received": "jarvis",
        "lead.qualified": "jarvis",
        "document.sample.requested": "intake",
        "document.sample.received": "docai",
        "docai.analysis.requested": "docai",
        "docai.analysis.completed": "jarvis",
        "proposal.draft.generated": "jarvis",
        "approval.required": "approval_gw",
        "approval.granted": "jarvis",
        "approval.rejected": "jarvis",
        "workflow.transitioned": "jarvis",
        "workflow.failed": "notifications",
    }
    return mapping.get(event_type, "jarvis")
