"""Celery tasks for durable approval monitoring."""
from __future__ import annotations

from celery import shared_task

from approvals.gateway import ApprovalGateway


@shared_task
def scan_pending_approvals() -> dict[str, int]:
    """Sweep persisted approvals for escalation and expiration."""
    return ApprovalGateway.sweep_due_approvals()
