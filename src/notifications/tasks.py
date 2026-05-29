"""Celery tasks for the durable notification pipeline."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="notifications.retry_pending", max_retries=0)
def retry_pending_notifications(limit: int = 50) -> dict:
    """Sweep due notifications and retry delivery. Scheduled by Celery Beat."""
    from notifications.durable_service import DurableNotificationService

    return DurableNotificationService.retry_pending_sync(limit=limit)
