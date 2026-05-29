"""
Executive overlay for Jarvis (Sprint 4 / B3).

Aggregates commercial KPIs (B1) and operational risk signals on top of the
existing Jarvis briefing. Designed to be called from
``JarvisAgent.generate_briefing`` and is safe to fail (caller wraps in
try/except so the legacy briefing keeps working).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from django.db.models import Avg, Count, Sum
from django.utils import timezone

from core.tenants import INTERNAL_TENANT_ID


def _commercial_snapshot(tenant_id: str) -> dict[str, Any]:
    from commercial.enums import ACTIVE_OPPORTUNITY_STAGES, LeadStatus, OpportunityStage
    from commercial.models import FollowUpDraft, Lead, Opportunity

    leads = Lead.objects.filter(tenant_id=tenant_id)
    opps = Opportunity.objects.filter(tenant_id=tenant_id)

    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    leads_total = leads.count()
    leads_24h = leads.filter(created_at__gte=last_24h).count()
    hot_leads_qs = leads.filter(score__gte=70).exclude(status=LeadStatus.DISQUALIFIED)
    hot_leads_count = hot_leads_qs.count()

    # Hot leads with no activity in 24h are at risk of going cold.
    hot_stale = hot_leads_qs.filter(last_event_at__lt=last_24h).count()

    active_value = (
        opps.filter(stage__in=ACTIVE_OPPORTUNITY_STAGES)
        .aggregate(s=Sum("estimated_value"))["s"]
        or 0
    )
    won_value = (
        opps.filter(stage=OpportunityStage.WON, closed_at__gte=last_7d)
        .aggregate(s=Sum("estimated_value"))["s"]
        or 0
    )

    pending_followups = FollowUpDraft.objects.filter(
        tenant_id=tenant_id, status=FollowUpDraft.Status.PENDING_APPROVAL
    ).count()

    top_hot = list(
        hot_leads_qs.order_by("-score", "-last_event_at")[:5].values(
            "lead_id", "company_name", "score", "status"
        )
    )

    return {
        "leads_total": leads_total,
        "leads_last_24h": leads_24h,
        "hot_leads": hot_leads_count,
        "hot_leads_stale_24h": hot_stale,
        "opportunities_active": opps.filter(stage__in=ACTIVE_OPPORTUNITY_STAGES).count(),
        "opportunities_won_7d": opps.filter(
            stage=OpportunityStage.WON, closed_at__gte=last_7d
        ).count(),
        "pipeline_value_active": float(active_value),
        "revenue_won_7d": float(won_value),
        "pending_followup_drafts": pending_followups,
        "avg_lead_score": leads.aggregate(a=Avg("score"))["a"] or 0,
        "top_hot_leads": top_hot,
    }


def build_executive_overlay(tenant_id: Optional[str] = None) -> dict[str, Any]:
    """
    Build the commercial / executive overlay for the daily briefing.

    Returns a dict with keys: ``commercial``, ``alerts``, ``top_priorities``.
    """
    tenant = tenant_id or INTERNAL_TENANT_ID
    snap = _commercial_snapshot(tenant)

    alerts: list[str] = []
    if snap["hot_leads_stale_24h"] > 0:
        alerts.append(
            f"{snap['hot_leads_stale_24h']} lead(s) quente(s) sem atividade há mais de 24h"
        )
    if snap["pending_followup_drafts"] > 0:
        alerts.append(
            f"{snap['pending_followup_drafts']} follow-up(s) aguardando aprovação"
        )
    if snap["opportunities_active"] == 0 and snap["leads_total"] > 0:
        alerts.append("Nenhuma oportunidade ativa no pipeline — investigar conversão")

    # Top 3 priorities for the day, action-first.
    priorities: list[dict[str, str]] = []
    for hot in snap["top_hot_leads"][:3]:
        priorities.append({
            "type": "hot_lead",
            "title": f"Acionar lead quente: {hot['company_name'] or hot['lead_id']}",
            "detail": f"Score {hot['score']} · status {hot['status']}",
            "action": f"Abrir lead {hot['lead_id']} → gerar follow-up ou agendar demo.",
            "ref": hot["lead_id"],
        })
    if snap["pending_followup_drafts"] > 0:
        priorities.append({
            "type": "approval",
            "title": "Aprovar follow-ups pendentes",
            "detail": f"{snap['pending_followup_drafts']} rascunho(s) aguardando",
            "action": "Abrir fila de approvals e revisar mensagens.",
            "ref": "followups",
        })

    return {
        "commercial": snap,
        "alerts": alerts,
        "top_priorities": priorities[:5],
        "team": _team_snapshot(),
    }


def _team_snapshot() -> dict[str, Any]:
    """
    Summary of the digital team status and key metrics.
    Added in Phase 3 to reflect agents-as-team-members vision.
    """
    try:
        from agent_runtime.agent_charter import get_team_summary
        from agent_runtime.agent_metrics import compute_team_metrics

        team = get_team_summary()
        metrics = compute_team_metrics()
        active = sum(1 for a in team if a["status"] == "active")
        return {
            "total_agents": len(team),
            "active_agents": active,
            "agents": team,
            "metrics": metrics,
        }
    except Exception:
        return {"total_agents": 0, "active_agents": 0, "agents": [], "metrics": []}
