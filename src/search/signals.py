"""
Signals for automatic case re-indexing.

Triggers ``index_case_embedding`` Celery task whenever a CaseEvent is created.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="orchestrator.CaseEvent")
def reindex_case_on_event(sender, instance, created, **kwargs):
    """Queue case re-indexing when a new event arrives."""
    if not created:
        return
    try:
        from search.tasks import index_case_embedding

        index_case_embedding.delay(instance.case_id)
    except Exception:
        logger.debug("Could not queue case indexing", exc_info=True)
