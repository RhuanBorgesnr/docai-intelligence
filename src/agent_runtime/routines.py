"""
Agent Routines — proactive scheduled tasks for the digital team.

Each agent in the team has routines they execute periodically, just like
a real employee has daily/weekly responsibilities. These are Celery tasks
that get scheduled via celery-beat (or called manually from the ops dashboard).

Sprint 4 / Phase 3.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

from agent_runtime.prompt_registry import AgentType
from core.tenants import INTERNAL_TENANT_ID

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_routine(agent: str, routine: str, result: dict) -> dict:
    """Standard logging for routine execution."""
    logger.info("[%s] routine=%s result=%s", agent, routine, result.get("summary", "ok"))
    return result


# ── SDR Routines ──────────────────────────────────────────────────────────────

def sdr_stale_lead_check(tenant_id: str | None = None) -> dict[str, Any]:
    """
    SDR checks for hot leads (score ≥ 70) that have been inactive for >24h.
    Emits alerts so Theo can escalate.
    """
    from commercial.models import Lead, LeadScoreEvent
    from commercial.enums import LeadStatus

    tenant = tenant_id or INTERNAL_TENANT_ID
    cutoff = timezone.now() - timedelta(hours=24)

    stale = Lead.objects.filter(
        tenant_id=tenant,
        score__gte=70,
        last_event_at__lt=cutoff,
    ).exclude(
        status__in=[LeadStatus.DISQUALIFIED, LeadStatus.CONVERTED]
    ).order_by("-score")[:20]

    stale_list = []
    for lead in stale:
        hours_stale = (timezone.now() - lead.last_event_at).total_seconds() / 3600
        stale_list.append({
            "lead_id": lead.lead_id,
            "company": lead.company_name,
            "score": lead.score,
            "hours_stale": round(hours_stale, 1),
            "status": lead.status,
        })

    return _log_routine("SDR", "stale_lead_check", {
        "summary": f"{len(stale_list)} lead(s) quente(s) stale",
        "stale_leads": stale_list,
        "checked_at": timezone.now().isoformat(),
    })


# ── Sales Routines ────────────────────────────────────────────────────────────

def sales_followup_check(tenant_id: str | None = None) -> dict[str, Any]:
    """
    Sales checks for qualified leads that haven't received a follow-up in >12h.
    Generates follow-up drafts for each.
    """
    from commercial.models import Lead, FollowUpDraft
    from commercial.enums import LeadStatus

    tenant = tenant_id or INTERNAL_TENANT_ID
    cutoff = timezone.now() - timedelta(hours=12)

    qualified_no_followup = Lead.objects.filter(
        tenant_id=tenant,
        status=LeadStatus.QUALIFIED,
        last_event_at__lt=cutoff,
    ).exclude(
        followups__created_at__gte=cutoff,
    ).order_by("-score")[:10]

    needs_followup = []
    for lead in qualified_no_followup:
        hours_since = (timezone.now() - lead.last_event_at).total_seconds() / 3600
        needs_followup.append({
            "lead_id": lead.lead_id,
            "company": lead.company_name,
            "score": lead.score,
            "hours_since_activity": round(hours_since, 1),
        })

    return _log_routine("SALES", "followup_check", {
        "summary": f"{len(needs_followup)} lead(s) qualificado(s) sem follow-up recente",
        "leads_needing_followup": needs_followup,
        "checked_at": timezone.now().isoformat(),
    })


def sales_pipeline_stale_check(tenant_id: str | None = None) -> dict[str, Any]:
    """
    Sales checks for opportunities stuck in the same stage for >3 days.
    """
    from commercial.models import Opportunity
    from commercial.enums import ACTIVE_OPPORTUNITY_STAGES

    tenant = tenant_id or INTERNAL_TENANT_ID
    cutoff = timezone.now() - timedelta(days=3)

    stale_opps = Opportunity.objects.filter(
        tenant_id=tenant,
        stage__in=ACTIVE_OPPORTUNITY_STAGES,
        updated_at__lt=cutoff,
    ).select_related("lead").order_by("updated_at")[:10]

    stale_list = []
    for opp in stale_opps:
        days_stale = (timezone.now() - opp.updated_at).days
        stale_list.append({
            "opportunity_id": opp.opportunity_id,
            "company": opp.lead.company_name,
            "stage": opp.stage,
            "days_in_stage": days_stale,
            "value": float(opp.estimated_value),
        })

    return _log_routine("SALES", "pipeline_stale_check", {
        "summary": f"{len(stale_list)} oportunidade(s) parada(s) >3 dias",
        "stale_opportunities": stale_list,
        "checked_at": timezone.now().isoformat(),
    })


# ── DocAI Operator Routines ──────────────────────────────────────────────────

def docai_pending_demo_check(tenant_id: str | None = None) -> dict[str, Any]:
    """
    DocAI Operator checks for leads with documents uploaded but no demo run yet.
    """
    from commercial.models import Lead
    from commercial.enums import LeadStatus

    tenant = tenant_id or INTERNAL_TENANT_ID

    leads_with_docs = Lead.objects.filter(
        tenant_id=tenant,
        status__in=[LeadStatus.QUALIFIED, LeadStatus.NEW, LeadStatus.QUALIFYING],
    ).exclude(
        status=LeadStatus.DISQUALIFIED,
    )

    pending_demos = []
    for lead in leads_with_docs[:20]:
        docs = lead.payload.get("documents", [])
        insights = lead.payload.get("docai_insights", [])
        if docs and not insights:
            pending_demos.append({
                "lead_id": lead.lead_id,
                "company": lead.company_name,
                "score": lead.score,
                "documents_count": len(docs),
            })

    return _log_routine("DOCAI_OPERATOR", "pending_demo_check", {
        "summary": f"{len(pending_demos)} lead(s) com doc mas sem demo",
        "pending_demos": pending_demos,
        "checked_at": timezone.now().isoformat(),
    })


# ── Theo (Jarvis) Routines ───────────────────────────────────────────────────

def theo_daily_briefing(tenant_id: str | None = None) -> dict[str, Any]:
    """
    Theo generates the daily executive briefing with commercial KPIs,
    alerts, and top priorities.
    """
    from orchestrator.executive_signals import build_executive_overlay
    from agent_runtime.agent_metrics import compute_team_metrics

    tenant = tenant_id or INTERNAL_TENANT_ID

    overlay = build_executive_overlay(tenant)
    team_metrics = compute_team_metrics(tenant)

    briefing = {
        "commercial": overlay.get("commercial", {}),
        "alerts": overlay.get("alerts", []),
        "top_priorities": overlay.get("top_priorities", []),
        "team_performance": team_metrics,
        "generated_at": timezone.now().isoformat(),
        "generated_by": "theo",
    }

    return _log_routine("THEO", "daily_briefing", {
        "summary": f"{len(briefing['alerts'])} alertas, {len(briefing['top_priorities'])} prioridades",
        "briefing": briefing,
    })


def theo_agent_health_check() -> dict[str, Any]:
    """
    Theo checks the operational health of all agents in the team.
    """
    from agent_runtime.agent_charter import AGENT_TEAM, AgentStatus

    health = []
    for agent_type, charter in AGENT_TEAM.items():
        agent_health = {
            "agent_type": agent_type.value,
            "title": charter.title,
            "status": charter.status.value,
            "routines_total": len(charter.routines),
            "routines_enabled": sum(1 for r in charter.routines if r.enabled),
        }

        # Check if agent has any recent errors (simplified — in production
        # this would check Celery task results and error logs)
        agent_health["healthy"] = charter.status in (AgentStatus.ACTIVE, AgentStatus.STANDBY)
        health.append(agent_health)

    active_count = sum(1 for h in health if h["status"] == "active")
    total_count = len(health)

    return _log_routine("THEO", "agent_health_check", {
        "summary": f"{active_count}/{total_count} agentes ativos",
        "agents": health,
        "checked_at": timezone.now().isoformat(),
    })


def theo_escalation_sweep(tenant_id: str | None = None) -> dict[str, Any]:
    """
    Theo sweeps pending approvals and escalates those approaching SLA.
    """
    from approvals.gateway import ApprovalGateway

    swept = ApprovalGateway.sweep_due_approvals()

    return _log_routine("THEO", "escalation_sweep", {
        "summary": f"Sweep complete — {swept.get('escalated', 0)} escalado(s), "
                   f"{swept.get('expired', 0)} expirado(s)",
        "result": swept,
        "checked_at": timezone.now().isoformat(),
    })


# ── CS Routines ───────────────────────────────────────────────────────────────

def cs_customer_health_check(tenant_id: str | None = None) -> dict[str, Any]:
    """
    CS Agent calculates health score for active customers.
    Placeholder — will be fully implemented when customer models exist.
    """
    return _log_routine("CS", "customer_health_check", {
        "summary": "CS health check — aguardando modelo de Customer",
        "status": "standby",
        "checked_at": timezone.now().isoformat(),
    })


def cs_onboarding_followup(tenant_id: str | None = None) -> dict[str, Any]:
    """
    CS Agent checks for new customers that haven't completed onboarding.
    Placeholder — will be fully implemented when onboarding flow exists.
    """
    return _log_routine("CS", "onboarding_followup", {
        "summary": "CS onboarding followup — aguardando fluxo de onboarding",
        "status": "standby",
        "checked_at": timezone.now().isoformat(),
    })


# ── Intake Routines ───────────────────────────────────────────────────────────

def intake_webhook_health(tenant_id: str | None = None) -> dict[str, Any]:
    """
    Intake agent checks if webhooks are receiving leads normally.
    Compares last 4h intake volume against historical average.
    """
    from commercial.models import Lead

    tenant = tenant_id or INTERNAL_TENANT_ID
    now = timezone.now()
    last_4h = now - timedelta(hours=4)
    last_24h = now - timedelta(hours=24)

    recent = Lead.objects.filter(tenant_id=tenant, created_at__gte=last_4h).count()
    daily = Lead.objects.filter(tenant_id=tenant, created_at__gte=last_24h).count()

    expected_4h = max(daily / 6, 0)  # 4h is 1/6 of 24h
    anomaly = recent < (expected_4h * 0.3) if expected_4h > 2 else False

    return _log_routine("INTAKE", "webhook_health", {
        "summary": f"{recent} lead(s) nas últimas 4h (esperado ~{expected_4h:.0f})"
                   + (" ⚠️ ANOMALIA" if anomaly else ""),
        "leads_last_4h": recent,
        "leads_last_24h": daily,
        "expected_4h": round(expected_4h, 1),
        "anomaly_detected": anomaly,
        "checked_at": now.isoformat(),
    })


# ── Analyst Routines ──────────────────────────────────────────────────────────

def analyst_daily_metrics(tenant_id: str | None = None) -> dict[str, Any]:
    """
    Analyst captures daily snapshot of key operational metrics.
    """
    from agent_runtime.agent_metrics import compute_team_metrics

    tenant = tenant_id or INTERNAL_TENANT_ID
    metrics = compute_team_metrics(tenant)

    return _log_routine("ANALYST", "daily_metrics", {
        "summary": f"Snapshot de métricas — {len(metrics)} agentes medidos",
        "metrics": metrics,
        "captured_at": timezone.now().isoformat(),
    })


def analyst_weekly_funnel(tenant_id: str | None = None) -> dict[str, Any]:
    """
    Analyst generates weekly funnel report with conversion rates.
    """
    from commercial.models import Lead, Opportunity
    from commercial.enums import LeadStatus, OpportunityStage

    tenant = tenant_id or INTERNAL_TENANT_ID
    now = timezone.now()
    last_7d = now - timedelta(days=7)

    leads_7d = Lead.objects.filter(tenant_id=tenant, created_at__gte=last_7d)
    total = leads_7d.count()
    qualified = leads_7d.filter(status=LeadStatus.QUALIFIED).count()
    converted = leads_7d.filter(status=LeadStatus.CONVERTED).count()
    disqualified = leads_7d.filter(status=LeadStatus.DISQUALIFIED).count()

    opps_7d = Opportunity.objects.filter(tenant_id=tenant, created_at__gte=last_7d)
    demos = opps_7d.filter(stage__in=[OpportunityStage.DEMO_SCHEDULED, OpportunityStage.DEMO_DONE]).count()
    proposals = opps_7d.filter(stage=OpportunityStage.PROPOSAL_SENT).count()
    won = opps_7d.filter(stage=OpportunityStage.WON).count()

    funnel = {
        "period": "7d",
        "leads_total": total,
        "leads_qualified": qualified,
        "leads_converted": converted,
        "leads_disqualified": disqualified,
        "conversion_lead_to_qualified": round(qualified / total * 100, 1) if total else 0,
        "conversion_qualified_to_opp": round(converted / qualified * 100, 1) if qualified else 0,
        "demos_scheduled": demos,
        "proposals_sent": proposals,
        "deals_won": won,
    }

    return _log_routine("ANALYST", "weekly_funnel", {
        "summary": f"Funil 7d: {total} leads → {qualified} qualified → {converted} converted → {won} won",
        "funnel": funnel,
        "generated_at": now.isoformat(),
    })


# ── Celery Beat Schedule ─────────────────────────────────────────────────────

def get_celery_beat_schedule() -> dict:
    """
    Returns the celery-beat schedule configuration for all agent routines.
    Add this to CELERY_BEAT_SCHEDULE in settings.py.
    """
    from celery.schedules import crontab

    return {
        # SDR
        "sdr-qualify-pending": {
            "task": "commercial.tasks.qualify_pending_leads_batch",
            "schedule": crontab(minute=0),  # Every hour
        },
        "sdr-stale-lead-check": {
            "task": "agent_runtime.routines.sdr_stale_lead_check",
            "schedule": crontab(minute=0, hour="*/4"),  # Every 4h
        },
        # Sales
        "sales-followup-check": {
            "task": "agent_runtime.routines.sales_followup_check",
            "schedule": crontab(minute=30, hour="*/4"),  # Every 4h at :30
        },
        "sales-pipeline-stale": {
            "task": "agent_runtime.routines.sales_pipeline_stale_check",
            "schedule": crontab(minute=0, hour=8),  # Daily at 8am
        },
        # DocAI Operator
        "docai-pending-demo": {
            "task": "agent_runtime.routines.docai_pending_demo_check",
            "schedule": crontab(minute=15, hour="*/4"),  # Every 4h at :15
        },
        # Theo
        "theo-daily-briefing": {
            "task": "agent_runtime.routines.theo_daily_briefing",
            "schedule": crontab(minute=0, hour=7),  # Daily at 7am
        },
        "theo-health-check": {
            "task": "agent_runtime.routines.theo_agent_health_check",
            "schedule": crontab(minute=45),  # Every hour at :45
        },
        "theo-escalation-sweep": {
            "task": "agent_runtime.routines.theo_escalation_sweep",
            "schedule": crontab(minute="*/30"),  # Every 30 min
        },
        # CS
        "cs-health-check": {
            "task": "agent_runtime.routines.cs_customer_health_check",
            "schedule": crontab(minute=0, hour=9),  # Daily at 9am
        },
        "cs-onboarding": {
            "task": "agent_runtime.routines.cs_onboarding_followup",
            "schedule": crontab(minute=0, hour=10),  # Daily at 10am
        },
        # Intake
        "intake-webhook-health": {
            "task": "agent_runtime.routines.intake_webhook_health",
            "schedule": crontab(minute=0, hour="*/4"),  # Every 4h
        },
        # Analyst
        "analyst-daily-metrics": {
            "task": "agent_runtime.routines.analyst_daily_metrics",
            "schedule": crontab(minute=0, hour=23),  # Daily at 11pm
        },
        "analyst-weekly-funnel": {
            "task": "agent_runtime.routines.analyst_weekly_funnel",
            "schedule": crontab(minute=0, hour=8, day_of_week=1),  # Monday 8am
        },
    }
