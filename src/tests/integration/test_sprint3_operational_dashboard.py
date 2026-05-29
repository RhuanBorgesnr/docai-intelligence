"""
Sprint 3 – Bloco 3: Operational Dashboard Integration Tests.

Tests the dashboard service layer and API endpoints for:
- Case pipeline metrics
- Case throughput
- Approval summary
- Notification metrics
- System health
- Agent status topology
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone as dj_timezone

from approvals.models import Approval
from notifications.models import Notification, NotificationProviderHealth
from orchestrator.dashboard import (
    get_agent_status,
    get_approval_summary,
    get_case_pipeline,
    get_case_throughput,
    get_notification_metrics,
    get_operational_summary,
    get_system_health,
)
from orchestrator.enums import ApprovalStatus, Priority
from orchestrator.models import Case, CaseEvent, DLQEvent


# ── helpers ───────────────────────────────────────────────────────────────────

def _case(ref, state="new", tenant="t1", **kw):
    return Case.objects.create(
        external_ref=ref,
        tenant_id=tenant,
        title=kw.get("title", f"Case {ref}"),
        state=state,
        priority=kw.get("priority", Priority.MEDIUM),
        correlation_id=f"corr-{ref}",
        trace_id=f"trace-{ref}",
    )


def _event(case, event_type="lead.received"):
    return CaseEvent.objects.create(
        event_id=f"evt-{case.external_ref}-{event_type}-{CaseEvent.objects.count()}",
        case=case,
        event_type=event_type,
        event_version="1.0",
        source="test",
        priority=Priority.MEDIUM,
        occurred_at=dj_timezone.now(),
        correlation_id=case.correlation_id,
        trace_id=case.trace_id,
        payload={},
    )


def _approval(case, status=ApprovalStatus.PENDING, atype="financial"):
    return Approval.objects.create(
        approval_id=f"apv-{case.external_ref}-{Approval.objects.count()}",
        case=case,
        approval_type=atype,
        status=status,
        requested_by_agent="analyzer",
        tenant_id=case.tenant_id,
        summary=f"Approval for {case.external_ref}",
    )


def _notification(case, channel="email", status="pending"):
    return Notification.objects.create(
        notification_id=f"ntf-{case.external_ref}-{Notification.objects.count()}",
        case=case,
        tenant_id=case.tenant_id,
        channel=channel,
        recipient="test@example.com",
        message="Test notification",
        status=status,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Case Pipeline
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_case_pipeline_by_state():
    """get_case_pipeline groups cases by state correctly."""
    _case("pip-1", state="new")
    _case("pip-2", state="triage")
    _case("pip-3", state="won")
    _case("pip-4", state="failed")

    result = get_case_pipeline()

    assert result["total"] == 4
    assert result["by_state"]["new"] == 1
    assert result["by_state"]["triage"] == 1
    assert result["by_state"]["won"] == 1
    assert result["active"] == 2  # new + triage
    assert result["completed"] == 1  # won
    assert result["failed"] == 1


@pytest.mark.django_db(transaction=True)
def test_case_pipeline_tenant_filter():
    """get_case_pipeline respects tenant filter."""
    _case("pip-ta", state="new", tenant="alpha")
    _case("pip-tb", state="new", tenant="beta")

    result = get_case_pipeline(tenant_id="alpha")

    assert result["total"] == 1
    assert result["by_state"]["new"] == 1


@pytest.mark.django_db(transaction=True)
def test_case_pipeline_by_priority():
    """get_case_pipeline groups by priority."""
    _case("pip-p1", priority=Priority.HIGH)
    _case("pip-p2", priority=Priority.LOW)
    _case("pip-p3", priority=Priority.HIGH)

    result = get_case_pipeline()

    assert result["by_priority"]["high"] == 2
    assert result["by_priority"]["low"] == 1


# ══════════════════════════════════════════════════════════════════════════════
#  Case Throughput
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_case_throughput_counts_recent():
    """get_case_throughput counts cases created in the period."""
    _case("tp-1")
    _case("tp-2")
    _case("tp-3", state="won")

    result = get_case_throughput(days=30)

    assert result["period_days"] == 30
    assert result["created"] == 3
    assert result["completed"] == 1  # won


# ══════════════════════════════════════════════════════════════════════════════
#  Approval Summary
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_approval_summary_counts():
    """get_approval_summary aggregates approval statuses."""
    c = _case("apv-s1")
    _approval(c, status=ApprovalStatus.PENDING)
    _approval(c, status=ApprovalStatus.APPROVED)
    _approval(c, status=ApprovalStatus.REJECTED)
    _approval(c, status=ApprovalStatus.EXPIRED)

    result = get_approval_summary()

    assert result["total"] == 4
    assert result["pending"] == 1
    assert result["approved"] == 1
    assert result["rejected"] == 1
    assert result["expired"] == 1


@pytest.mark.django_db(transaction=True)
def test_approval_summary_overdue():
    """get_approval_summary counts overdue approvals."""
    c = _case("apv-od")
    apv = _approval(c, status=ApprovalStatus.PENDING)
    apv.deadline_at = dj_timezone.now() - timedelta(hours=1)
    apv.save()

    result = get_approval_summary()

    assert result["overdue"] == 1


@pytest.mark.django_db(transaction=True)
def test_approval_summary_by_type():
    """get_approval_summary groups by approval_type."""
    c = _case("apv-bt")
    _approval(c, atype="financial")
    _approval(c, atype="legal")
    _approval(c, atype="financial")

    result = get_approval_summary()

    assert result["by_type"]["financial"] == 2
    assert result["by_type"]["legal"] == 1


# ══════════════════════════════════════════════════════════════════════════════
#  Notification Metrics
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_notification_metrics_by_status():
    """get_notification_metrics aggregates delivery statuses."""
    c = _case("ntf-m1")
    _notification(c, status="sent")
    _notification(c, status="sent")
    _notification(c, status="failed")
    _notification(c, status="pending")

    result = get_notification_metrics()

    assert result["total"] == 4
    assert result["sent"] == 2
    assert result["failed"] == 1
    assert result["pending"] == 1


@pytest.mark.django_db(transaction=True)
def test_notification_metrics_by_channel():
    """get_notification_metrics breaks down per channel."""
    c = _case("ntf-ch")
    _notification(c, channel="email", status="sent")
    _notification(c, channel="telegram", status="sent")
    _notification(c, channel="telegram", status="failed")

    result = get_notification_metrics()

    assert result["by_channel"]["email"]["sent"] == 1
    assert result["by_channel"]["telegram"]["sent"] == 1
    assert result["by_channel"]["telegram"]["failed"] == 1


@pytest.mark.django_db(transaction=True)
def test_notification_metrics_dead_letter():
    """get_notification_metrics counts dead-lettered notifications."""
    c = _case("ntf-dl")
    n = _notification(c, status="failed")
    n.is_dead = True
    n.save()

    result = get_notification_metrics()

    assert result["dead_letter"] == 1


# ══════════════════════════════════════════════════════════════════════════════
#  System Health
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_system_health_circuit_breakers():
    """get_system_health reports circuit breaker state."""
    NotificationProviderHealth.objects.create(
        channel="email", is_open=False, failure_count=2, success_count=10,
    )
    NotificationProviderHealth.objects.create(
        channel="telegram", is_open=True, failure_count=5, success_count=3,
    )

    result = get_system_health()

    assert len(result["circuit_breakers"]) == 2
    telegram = next(cb for cb in result["circuit_breakers"] if cb["channel"] == "telegram")
    assert telegram["is_open"] is True


@pytest.mark.django_db(transaction=True)
def test_system_health_dlq():
    """get_system_health counts DLQ events."""
    c = _case("dlq-h1")
    evt = _event(c)
    DLQEvent.objects.create(
        case=c, original_event=evt, reason_code="processing_error", error_message="timeout",
    )

    result = get_system_health()

    assert result["dlq_size"] == 1


@pytest.mark.django_db(transaction=True)
def test_system_health_pending_counts():
    """get_system_health reports pending notification and approval counts."""
    c = _case("hlth-p")
    _notification(c, status="pending")
    _notification(c, status="pending")
    _approval(c, status=ApprovalStatus.PENDING)

    result = get_system_health()

    assert result["pending_notifications"] == 2
    assert result["pending_approvals"] == 1


# ══════════════════════════════════════════════════════════════════════════════
#  Agent Status (Visual Dashboard)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_agent_status_returns_all_agents():
    """get_agent_status returns the full agent topology."""
    result = get_agent_status()

    agent_ids = [a["id"] for a in result["agents"]]
    assert "jarvis" in agent_ids
    assert "intake" in agent_ids
    assert "sdr" in agent_ids
    assert "sales" in agent_ids
    assert "docai" in agent_ids
    assert "approval_gw" in agent_ids
    assert "notifications" in agent_ids
    assert "memory_rag" in agent_ids
    assert len(result["agents"]) == 8


@pytest.mark.django_db(transaction=True)
def test_agent_status_jarvis_active():
    """Jarvis shows active when cases exist."""
    _case("ag-j1", state="triage")

    result = get_agent_status()

    jarvis = next(a for a in result["agents"] if a["id"] == "jarvis")
    assert jarvis["status"] == "active"
    assert jarvis["queue_size"] >= 1


@pytest.mark.django_db(transaction=True)
def test_agent_status_intake_active():
    """Intake agent is active when cases are in new/triage state."""
    _case("ag-in1", state="new")
    _case("ag-in2", state="triage")

    result = get_agent_status()

    intake = next(a for a in result["agents"] if a["id"] == "intake")
    assert intake["status"] == "active"
    assert intake["queue_size"] == 2


@pytest.mark.django_db(transaction=True)
def test_agent_status_approval_gw_warning_on_overdue():
    """Approval gateway shows warning when overdue approvals exist."""
    c = _case("ag-apv-w")
    apv = _approval(c, status=ApprovalStatus.PENDING)
    apv.deadline_at = dj_timezone.now() - timedelta(hours=2)
    apv.save()

    result = get_agent_status()

    gw = next(a for a in result["agents"] if a["id"] == "approval_gw")
    assert gw["status"] == "warning"
    assert gw["error_count"] >= 1


@pytest.mark.django_db(transaction=True)
def test_agent_status_notifications_error():
    """Notification service shows error when failed notifications exist."""
    c = _case("ag-ntf-e")
    _notification(c, status="failed")

    result = get_agent_status()

    notif = next(a for a in result["agents"] if a["id"] == "notifications")
    assert notif["status"] == "error"
    assert notif["error_count"] >= 1


@pytest.mark.django_db(transaction=True)
def test_agent_status_includes_recent_events():
    """get_agent_status returns recent events with source/target mapping."""
    c = _case("ag-evt")
    _event(c, "lead.received")
    _event(c, "lead.qualified")

    result = get_agent_status()

    assert len(result["recent_events"]) >= 2
    evt0 = result["recent_events"][0]
    assert "type" in evt0
    assert "source" in evt0
    assert "target" in evt0
    assert "timestamp" in evt0


@pytest.mark.django_db(transaction=True)
def test_agent_status_summary():
    """get_agent_status summary contains all required keys."""
    _case("ag-sum", state="triage")
    c2 = _case("ag-sum2")
    _approval(c2, status=ApprovalStatus.PENDING)
    _notification(c2, status="pending")

    result = get_agent_status()

    summary = result["summary"]
    assert summary["active_cases"] >= 2
    assert summary["pending_approvals"] >= 1
    assert summary["pending_notifications"] >= 1
    assert "dlq_size" in summary


# ══════════════════════════════════════════════════════════════════════════════
#  Operational Summary (full)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_operational_summary_structure():
    """get_operational_summary returns all sections."""
    result = get_operational_summary()

    assert "pipeline" in result
    assert "throughput" in result
    assert "approvals" in result
    assert "notifications" in result
    assert "health" in result
    assert "generated_at" in result
