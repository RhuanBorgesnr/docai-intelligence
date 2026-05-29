"""Celery tasks for event processing and workflow transitions."""
from __future__ import annotations

import logging

from celery import shared_task

from audit.services import write_audit_log
from orchestrator.durable_events import (
    claim_pending_outbox_batch,
    mark_event_processed,
    mark_outbox_failed,
    mark_outbox_published,
)
from orchestrator.models import CaseEvent, DLQEvent, EventOutbox
from orchestrator.workflow import apply_transition

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5)
def process_received_event(self, case_event_id: int) -> None:
    """Entry point task for processing a newly ingested event."""
    try:
        execute_workflow_transition.delay(case_event_id)
    except Exception as exc:
        logger.exception("Failed to enqueue workflow transition for event=%s", case_event_id)
        raise self.retry(exc=exc, countdown=30)


@shared_task(bind=True, max_retries=3)
def execute_workflow_transition(self, case_event_id: int) -> None:
    """Apply workflow transition for a case event."""
    try:
        event = CaseEvent.objects.select_related("case").get(pk=case_event_id)
        if not mark_event_processed(consumer="workflow.transition", event=event):
            return
        result = apply_transition(event)
        write_audit_log(
            action="workflow.transition.executed",
            case_id=event.case_id,
            trace_id=event.trace_id,
            correlation_id=event.correlation_id,
            details={
                "event_id": event.event_id,
                "changed": result.changed,
                "from": result.previous_state,
                "to": result.new_state,
                "emitted_events": result.emitted_event_types,
            },
        )
        # Trigger Jarvis evaluation after successful transition
        if result.changed:
            try:
                jarvis_evaluate_case.delay(event.case_id)
            except Exception:
                logger.debug("Could not enqueue Jarvis evaluation", exc_info=True)
    except Exception as exc:
        logger.exception("Workflow transition failed for event=%s", case_event_id)
        send_event_to_dlq.delay(case_event_id=case_event_id, reason_code="WORKFLOW_TRANSITION_ERROR", error_message=str(exc))
        raise self.retry(exc=exc, countdown=60)


@shared_task
def send_event_to_dlq(case_event_id: int, reason_code: str, error_message: str = "") -> int | None:
    """Persist failed event details into DLQ."""
    try:
        event = CaseEvent.objects.select_related("case").get(pk=case_event_id)
    except CaseEvent.DoesNotExist:
        return None

    dlq_event = DLQEvent.objects.create(
        case=event.case,
        original_event=event,
        reason_code=reason_code,
        error_message=error_message,
        attempts=1,
        payload={
            "event_id": event.event_id,
            "event_type": event.event_type,
            "payload": event.payload,
        },
        trace_id=event.trace_id,
    )

    write_audit_log(
        action="workflow.event.sent_to_dlq",
        case_id=event.case_id,
        trace_id=event.trace_id,
        correlation_id=event.correlation_id,
        details={
            "event_id": event.event_id,
            "dlq_event_id": dlq_event.id,
            "reason_code": reason_code,
        },
    )

    return dlq_event.id


@shared_task(bind=True, max_retries=5)
def publish_pending_outbox(self, limit: int = 100) -> int:
    """Claim and publish a batch of durable outbox events."""
    published = 0
    outbox_batch = claim_pending_outbox_batch(limit=limit)

    for outbox in outbox_batch:
        try:
            logger.info(
                "Publishing durable event %s type=%s source=%s",
                outbox.event_id,
                outbox.event_type,
                outbox.source,
            )
            mark_outbox_published(outbox)
            published += 1
        except Exception as exc:
            logger.exception("Failed publishing outbox event=%s", outbox.event_id)
            mark_outbox_failed(outbox, str(exc))

    return published


# ── Jarvis Agent Tasks ───────────────────────────────────────────────────────

@shared_task(name="orchestrator.jarvis_evaluate_case", max_retries=2, default_retry_delay=15)
def jarvis_evaluate_case(case_id: int) -> dict:
    """
    Trigger Jarvis to evaluate a case and dispatch to the appropriate specialist.

    Called automatically after workflow transitions, or on-demand.
    """
    from orchestrator.jarvis_agent import JarvisAgent

    try:
        jarvis = JarvisAgent()
        return jarvis.process_event(case_id)
    except Exception as exc:
        logger.exception("[jarvis] failed evaluating case=%s: %s", case_id, exc)
        raise jarvis_evaluate_case.retry(exc=exc)


@shared_task(name="orchestrator.jarvis_briefing")
def jarvis_generate_briefing(tenant_id: str | None = None) -> dict:
    """
    Generate an executive briefing.  Scheduled via Celery Beat for daily runs.
    """
    from orchestrator.jarvis_agent import JarvisAgent

    jarvis = JarvisAgent()
    briefing = jarvis.generate_briefing(tenant_id=tenant_id)
    logger.info(
        "[jarvis] briefing generated — %d alerts, %d active cases",
        briefing["alert_count"],
        briefing["summary"]["active_cases"],
    )
    return briefing
