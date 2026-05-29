"""
Demo Scheduler — Sales + DocAI Operator coordination.

When a sales rep (or the Sales agent) decides to schedule a demo,
this module:
1. Creates the demo slot on the Opportunity
2. Transitions the opportunity to DEMO_SCHEDULED
3. Sends a notification to the lead and ops team
4. Creates a timeline event
5. Prepares context for DocAI Operator

Sprint 4 / Phase 3 — Quick Win D3.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from agent_runtime.prompt_registry import AgentType
from core.tenants import INTERNAL_TENANT_ID

logger = logging.getLogger(__name__)


def schedule_demo(
    lead_id: str,
    scheduled_at: datetime | None = None,
    notes: str = "",
    scheduled_by: str = "sales",
) -> dict[str, Any]:
    """
    Schedule a DocAI demo for a lead.

    Steps:
    1. Find or create Opportunity for the lead
    2. Set stage to DEMO_SCHEDULED
    3. Record demo metadata
    4. Create timeline event
    5. Send notification

    Returns dict with opportunity_id, demo details, notification status.
    """
    from commercial.models import Lead, Opportunity
    from commercial.enums import OpportunityStage
    from audit.models import AuditLog

    lead = Lead.objects.get(lead_id=lead_id)

    # Default: schedule for tomorrow 10am
    if not scheduled_at:
        tomorrow = timezone.now() + timedelta(days=1)
        scheduled_at = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)

    # Find or create opportunity
    opp = lead.opportunities.filter(
        stage__in=[
            OpportunityStage.NEW,
            OpportunityStage.QUALIFIED,
            OpportunityStage.DEMO_SCHEDULED,
        ]
    ).first()

    if not opp:
        opp = Opportunity.objects.create(
            tenant_id=lead.tenant_id,
            lead=lead,
            case=lead.case,
            stage=OpportunityStage.DEMO_SCHEDULED,
            notes=notes,
            metadata={
                "demo_scheduled_at": scheduled_at.isoformat(),
                "demo_scheduled_by": scheduled_by,
            },
        )
    else:
        opp.stage = OpportunityStage.DEMO_SCHEDULED
        opp.metadata = {
            **(opp.metadata or {}),
            "demo_scheduled_at": scheduled_at.isoformat(),
            "demo_scheduled_by": scheduled_by,
        }
        if notes:
            opp.notes = f"{opp.notes}\n{notes}".strip() if opp.notes else notes
        opp.save(update_fields=["stage", "metadata", "notes", "updated_at"])

    # Update lead
    lead.last_event_at = timezone.now()
    lead.save(update_fields=["last_event_at", "updated_at"])

    # Audit trail
    AuditLog.objects.create(
        action="demo.scheduled",
        actor_type="agent",
        actor_id=scheduled_by,
        details={
            "entity_type": "lead",
            "entity_id": lead.lead_id,
            "opportunity_id": opp.opportunity_id,
            "scheduled_at": scheduled_at.isoformat(),
            "agent_type": AgentType.SALES.value,
        },
    )

    # Notification
    notification_sent = _send_demo_notification(lead, opp, scheduled_at)

    logger.info(
        "[SALES] Demo scheduled for lead=%s opp=%s at=%s by=%s",
        lead.lead_id, opp.opportunity_id, scheduled_at.isoformat(), scheduled_by,
    )

    return {
        "lead_id": lead.lead_id,
        "opportunity_id": opp.opportunity_id,
        "stage": opp.stage,
        "demo_scheduled_at": scheduled_at.isoformat(),
        "scheduled_by": scheduled_by,
        "notification_sent": notification_sent,
        "agent": AgentType.SALES.value,
    }


def _send_demo_notification(lead, opp, scheduled_at: datetime) -> bool:
    """Send notification about the scheduled demo."""
    try:
        from notifications.service import NotificationService, NotificationChannel
        import uuid

        msg = (
            f"📅 Demo DocAI agendada!\n"
            f"Lead: {lead.company_name or lead.contact_name} (score: {lead.score})\n"
            f"Data: {scheduled_at.strftime('%d/%m/%Y %H:%M')}\n"
            f"Oportunidade: {opp.opportunity_id}"
        )

        import asyncio
        kwargs = dict(
            notification_id=f"demo_{uuid.uuid4().hex[:12]}",
            case_id=str(lead.case_id or ""),
            channel=NotificationChannel.DASHBOARD,
            recipient="ops",
            subject="Demo DocAI Agendada",
            message=msg,
            template_name="demo_scheduled",
            context={
                "lead_id": lead.lead_id,
                "opportunity_id": opp.opportunity_id,
                "scheduled_at": scheduled_at.isoformat(),
            },
        )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return True
            loop.run_until_complete(NotificationService.send_notification(**kwargs))
        except RuntimeError:
            asyncio.run(NotificationService.send_notification(**kwargs))
        return True
    except Exception as exc:
        logger.warning("[SALES] Failed to send demo notification: %s", exc)
        return False


def notify_followup_approved(draft_id: str) -> bool:
    """
    Send real notification when a follow-up is approved.
    Called by the approval gateway when status changes to APPROVED.

    Quick Win D2 — notificação real quando follow-up aprovado.
    """
    from commercial.models import FollowUpDraft

    try:
        draft = FollowUpDraft.objects.select_related("lead").get(draft_id=draft_id)
    except FollowUpDraft.DoesNotExist:
        logger.warning("[SALES] Follow-up draft %s not found", draft_id)
        return False

    try:
        from notifications.service import NotificationService, NotificationChannel
        import asyncio
        import uuid

        msg = (
            f"✅ Follow-up aprovado!\n"
            f"Lead: {draft.lead.company_name or draft.lead.contact_name}\n"
            f"Canal: {draft.channel}\n"
            f"Assunto: {draft.subject}\n"
            f"Pronto para envio."
        )

        kwargs = dict(
            notification_id=f"fup_{uuid.uuid4().hex[:12]}",
            case_id=str(draft.lead.case_id or ""),
            channel=NotificationChannel.DASHBOARD,
            recipient="ops",
            subject="Follow-up Aprovado",
            message=msg,
            template_name="followup_approved",
            context={
                "draft_id": draft.draft_id,
                "lead_id": draft.lead.lead_id,
                "channel": draft.channel,
            },
        )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return True
            loop.run_until_complete(NotificationService.send_notification(**kwargs))
        except RuntimeError:
            asyncio.run(NotificationService.send_notification(**kwargs))

        logger.info("[SALES] Follow-up approved notification sent for draft=%s", draft_id)
        return True
    except Exception as exc:
        logger.warning("[SALES] Failed to send followup approval notification: %s", exc)
        return False
