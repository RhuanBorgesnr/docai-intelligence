"""
Celery tasks for the search / semantic memory subsystem.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="search.index_case_embedding", max_retries=2, default_retry_delay=10)
def index_case_embedding(case_id: int) -> bool:
    """
    Upsert the CaseEmbedding for *case_id*.

    Called automatically via signal when a CaseEvent is created,
    or on-demand from management commands / other tasks.
    """
    from search.services import index_case

    try:
        return index_case(case_id)
    except Exception as exc:
        logger.exception("[search] failed to index case=%s: %s", case_id, exc)
        raise index_case_embedding.retry(exc=exc)
