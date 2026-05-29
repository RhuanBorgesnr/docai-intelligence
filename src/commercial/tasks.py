"""Celery tasks for the commercial domain."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=15)
def qualify_lead_task(self, lead_id: int) -> dict:
    """Run the SDR Agent against a lead asynchronously."""
    from commercial.services import qualify_lead

    try:
        outcome = qualify_lead(lead_id)
        return {
            "lead_id": outcome.lead.lead_id,
            "qualified": outcome.qualified,
            "confidence": outcome.confidence,
            "opportunity_id": (
                outcome.opportunity.opportunity_id if outcome.opportunity else None
            ),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("qualify_lead_task failed for lead_id=%s", lead_id)
        raise self.retry(exc=exc)


@shared_task
def run_docai_demo_task(lead_id: int, document_id: int) -> dict:
    """Run a DocAI demo + insight generation against a lead's document."""
    from commercial.docai_operator import run_docai_demo

    return run_docai_demo(lead_id=lead_id, document_id=document_id)


@shared_task
def qualify_pending_leads_batch() -> dict:
    """Qualify all leads that are still in NEW status (not yet processed by SDR)."""
    from commercial.models import Lead
    from commercial.services import qualify_lead

    pending = Lead.objects.filter(status="new").order_by("created_at")
    results = []
    for lead in pending:
        try:
            outcome = qualify_lead(lead.pk)
            results.append({
                "lead_id": lead.lead_id,
                "qualified": outcome.qualified,
                "confidence": outcome.confidence,
            })
        except Exception as exc:
            logger.warning("Batch qualify failed for %s: %s", lead.lead_id, exc)
            results.append({"lead_id": lead.lead_id, "error": str(exc)})

    return {
        "processed": len(results),
        "results": results,
    }
