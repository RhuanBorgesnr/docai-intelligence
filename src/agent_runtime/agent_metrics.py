"""
Agent Metrics — KPI computation for each digital team member.

Each agent has defined KPIs in their charter. This module computes
the actual values from the database, so the ops dashboard and Theo's
briefing show real performance data.

Sprint 4 / Phase 3.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Avg, Count, Q
from django.utils import timezone

from agent_runtime.prompt_registry import AgentType
from core.tenants import INTERNAL_TENANT_ID


def _safe_pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


# ── Per-Agent Metric Computation ──────────────────────────────────────────────

def compute_sdr_metrics(tenant_id: str) -> dict[str, Any]:
    from commercial.models import Lead, LeadScoreEvent
    from commercial.enums import LeadStatus

    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    leads = Lead.objects.filter(tenant_id=tenant_id)
    qualified_24h = leads.filter(
        status=LeadStatus.QUALIFIED,
        updated_at__gte=last_24h,
    ).count()

    # Average qualification time: time between created_at and the first
    # score_event that moved status to QUALIFIED
    score_events = LeadScoreEvent.objects.filter(
        lead__tenant_id=tenant_id,
        lead__status=LeadStatus.QUALIFIED,
        created_at__gte=last_7d,
    )
    qual_times = []
    for evt in score_events.select_related("lead")[:50]:
        delta = (evt.created_at - evt.lead.created_at).total_seconds() / 60
        if delta > 0:
            qual_times.append(delta)
    avg_qual_time = round(sum(qual_times) / len(qual_times), 1) if qual_times else None

    # Hot lead response time: time between lead creation and first activity
    hot_leads = leads.filter(score__gte=70, created_at__gte=last_7d)
    response_times = []
    for lead in hot_leads[:20]:
        first_event = lead.score_events.order_by("created_at").first()
        if first_event:
            delta = (first_event.created_at - lead.created_at).total_seconds() / 60
            if delta > 0:
                response_times.append(delta)
    avg_response_time = round(sum(response_times) / len(response_times), 1) if response_times else None

    # Qualification accuracy: qualified leads that became opportunities
    qualified_7d = leads.filter(status=LeadStatus.QUALIFIED, updated_at__gte=last_7d).count()
    converted_7d = leads.filter(status=LeadStatus.CONVERTED, updated_at__gte=last_7d).count()

    return {
        "agent": AgentType.SDR.value,
        "kpis": {
            "leads_qualified_24h": qualified_24h,
            "avg_qualification_time": avg_qual_time,
            "hot_lead_response_time": avg_response_time,
            "qualification_accuracy": _safe_pct(converted_7d, qualified_7d),
        },
        "period": "24h/7d",
    }


def compute_sales_metrics(tenant_id: str) -> dict[str, Any]:
    from commercial.models import FollowUpDraft, Opportunity
    from commercial.enums import ACTIVE_OPPORTUNITY_STAGES, OpportunityStage

    now = timezone.now()
    last_7d = now - timedelta(days=7)

    followups_sent = FollowUpDraft.objects.filter(
        tenant_id=tenant_id,
        status=FollowUpDraft.Status.SENT,
        sent_at__gte=last_7d,
    ).count()

    followups_approved = FollowUpDraft.objects.filter(
        tenant_id=tenant_id,
        status__in=[FollowUpDraft.Status.APPROVED, FollowUpDraft.Status.SENT],
        updated_at__gte=last_7d,
    ).count()

    opps = Opportunity.objects.filter(tenant_id=tenant_id)
    demos_7d = opps.filter(
        stage__in=[OpportunityStage.DEMO_SCHEDULED, OpportunityStage.DEMO_DONE],
        updated_at__gte=last_7d,
    ).count()

    pipeline_value = float(
        opps.filter(stage__in=ACTIVE_OPPORTUNITY_STAGES)
        .aggregate(total=Avg("estimated_value") * Count("id"))
        .get("total", 0) or 0
    )
    # Simplified: use Sum instead
    from django.db.models import Sum
    pipeline_value = float(
        opps.filter(stage__in=ACTIVE_OPPORTUNITY_STAGES)
        .aggregate(total=Sum("estimated_value"))["total"] or 0
    )

    qualified_7d = opps.filter(created_at__gte=last_7d).count()
    won_7d = opps.filter(stage=OpportunityStage.WON, closed_at__gte=last_7d).count()
    conversion = _safe_pct(won_7d, qualified_7d)

    return {
        "agent": AgentType.SALES.value,
        "kpis": {
            "followups_sent_7d": followups_sent,
            "followups_approved_7d": followups_approved,
            "demo_scheduled_7d": demos_7d,
            "conversion_rate": conversion,
            "pipeline_value": pipeline_value,
        },
        "period": "7d",
    }


def compute_docai_metrics(tenant_id: str) -> dict[str, Any]:
    from commercial.models import Lead

    now = timezone.now()
    last_7d = now - timedelta(days=7)

    leads = Lead.objects.filter(tenant_id=tenant_id)
    demos_run = 0
    insight_scores = []

    for lead in leads.filter(updated_at__gte=last_7d)[:50]:
        insights_list = lead.payload.get("docai_insights", [])
        for batch in insights_list:
            if isinstance(batch, dict) and batch.get("insights"):
                demos_run += 1
                for ins in batch["insights"]:
                    if isinstance(ins, dict) and "score" in ins:
                        insight_scores.append(ins["score"])

    avg_score = round(sum(insight_scores) / len(insight_scores), 1) if insight_scores else None
    avg_sources = None  # Would need RAG source tracking

    return {
        "agent": AgentType.DOCAI_OPERATOR.value,
        "kpis": {
            "demos_run_7d": demos_run,
            "avg_insight_score": avg_score,
            "total_insights_generated": len(insight_scores),
        },
        "period": "7d",
    }


def compute_theo_metrics(tenant_id: str) -> dict[str, Any]:
    from agent_runtime.agent_charter import AGENT_TEAM, AgentStatus

    active = sum(1 for c in AGENT_TEAM.values() if c.status == AgentStatus.ACTIVE)
    total = len(AGENT_TEAM)

    return {
        "agent": AgentType.JARVIS.value,
        "kpis": {
            "agent_uptime": _safe_pct(active, total),
            "team_size": total,
            "active_agents": active,
        },
        "period": "current",
    }


def compute_intake_metrics(tenant_id: str) -> dict[str, Any]:
    from commercial.models import Lead

    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    leads_24h = Lead.objects.filter(tenant_id=tenant_id, created_at__gte=last_24h).count()
    leads_7d = Lead.objects.filter(tenant_id=tenant_id, created_at__gte=last_7d).count()

    return {
        "agent": AgentType.INTAKE.value,
        "kpis": {
            "leads_received_24h": leads_24h,
            "leads_received_7d": leads_7d,
        },
        "period": "24h/7d",
    }


def compute_analyst_metrics(tenant_id: str) -> dict[str, Any]:
    return {
        "agent": AgentType.ANALYST.value,
        "kpis": {
            "reports_generated_7d": 0,  # Will be tracked when report model exists
        },
        "period": "7d",
    }


def compute_cs_metrics(tenant_id: str) -> dict[str, Any]:
    return {
        "agent": AgentType.SUPPORT.value,
        "kpis": {
            "customer_health_avg": None,  # Awaiting customer model
            "status": "standby",
        },
        "period": "current",
    }


# ── Aggregated Team Metrics ──────────────────────────────────────────────────

_METRIC_COMPUTERS = {
    AgentType.SDR: compute_sdr_metrics,
    AgentType.SALES: compute_sales_metrics,
    AgentType.DOCAI_OPERATOR: compute_docai_metrics,
    AgentType.JARVIS: compute_theo_metrics,
    AgentType.INTAKE: compute_intake_metrics,
    AgentType.ANALYST: compute_analyst_metrics,
    AgentType.SUPPORT: compute_cs_metrics,
}


def compute_team_metrics(tenant_id: str | None = None) -> list[dict[str, Any]]:
    """
    Compute KPIs for all agents in the team.
    Returns a list of per-agent metric dicts.
    """
    tenant = tenant_id or INTERNAL_TENANT_ID
    results = []
    for agent_type, fn in _METRIC_COMPUTERS.items():
        try:
            results.append(fn(tenant))
        except Exception as exc:
            results.append({
                "agent": agent_type.value,
                "kpis": {},
                "error": str(exc),
            })
    return results


def compute_agent_metrics(agent_type: AgentType, tenant_id: str | None = None) -> dict[str, Any]:
    """Compute KPIs for a single agent."""
    tenant = tenant_id or INTERNAL_TENANT_ID
    fn = _METRIC_COMPUTERS.get(agent_type)
    if not fn:
        return {"agent": agent_type.value, "kpis": {}, "error": "No metric computer"}
    return fn(tenant)
