"""Durable event persistence, outbox publication, and inbox deduplication."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from orchestrator.enums import DurableEventStatus
from orchestrator.models import Case, CaseEvent, EventInbox, EventOutbox

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DurableEventWriteResult:
    event: CaseEvent
    outbox: EventOutbox
    created: bool


def _payload_hash(payload: dict[str, Any], meta: dict[str, Any]) -> str:
    serialized = json.dumps({"payload": payload, "meta": meta}, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def persist_case_event(
    *,
    case: Case,
    event_id: str,
    event_type: str,
    event_version: str,
    source: str,
    priority: str,
    occurred_at,
    correlation_id: str,
    trace_id: str,
    tenant_id: str,
    payload: dict[str, Any],
    meta: dict[str, Any],
    causation_id: str = "",
) -> DurableEventWriteResult:
    """Persist a domain event and its outbox record atomically."""

    with transaction.atomic():
        try:
            event = CaseEvent.objects.create(
                event_id=event_id,
                case=case,
                event_type=event_type,
                event_version=event_version,
                source=source,
                priority=priority,
                occurred_at=occurred_at,
                correlation_id=correlation_id,
                trace_id=trace_id,
                payload=payload,
                meta=meta,
            )
            created = True
        except IntegrityError:
            event = CaseEvent.objects.select_related("case").get(event_id=event_id)
            created = False

        outbox_defaults = {
            "case": case,
            "event_type": event_type,
            "event_version": event_version,
            "source": source,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "trace_id": trace_id,
            "causation_id": causation_id,
            "payload": payload,
            "meta": {**meta, "payload_hash": _payload_hash(payload, meta)},
            "status": DurableEventStatus.PENDING,
        }
        outbox, _ = EventOutbox.objects.get_or_create(event_id=event_id, defaults=outbox_defaults)
        return DurableEventWriteResult(event=event, outbox=outbox, created=created)


def mark_event_processed(*, consumer: str, event: CaseEvent) -> bool:
    """Record inbox consumption once. Returns False when already processed."""

    payload_hash = _payload_hash(event.payload or {}, event.meta or {})
    try:
        with transaction.atomic():
            EventInbox.objects.create(
                consumer=consumer,
                event_id=event.event_id,
                event_type=event.event_type,
                tenant_id=event.case.tenant_id,
                correlation_id=event.correlation_id,
                trace_id=event.trace_id,
                payload_hash=payload_hash,
            )
            return True
    except IntegrityError:
        logger.info("Skipping duplicate event %s for consumer %s", event.event_id, consumer)
        return False


def persist_runtime_outbox_event(
    *,
    event_id: str,
    case: Case | None,
    event_type: str,
    source: str,
    tenant_id: str,
    correlation_id: str,
    trace_id: str,
    payload: dict[str, Any],
    meta: dict[str, Any] | None = None,
    causation_id: str = "",
    event_version: str = "1.0",
) -> EventOutbox:
    """Persist a runtime event directly into the outbox without requiring CaseEvent choices."""

    meta = meta or {}
    defaults = {
        "case": case,
        "event_type": event_type,
        "event_version": event_version,
        "source": source,
        "tenant_id": tenant_id,
        "correlation_id": correlation_id,
        "trace_id": trace_id,
        "causation_id": causation_id,
        "payload": payload,
        "meta": {**meta, "payload_hash": _payload_hash(payload, meta)},
        "status": DurableEventStatus.PENDING,
    }
    outbox, _ = EventOutbox.objects.get_or_create(event_id=event_id, defaults=defaults)
    return outbox


def claim_pending_outbox_batch(*, limit: int = 100, lease_seconds: int = 60) -> list[EventOutbox]:
    """Claim a batch of publishable events for one publisher worker."""

    now = timezone.now()
    lease_until = now + timezone.timedelta(seconds=lease_seconds)
    claimed: list[EventOutbox] = []

    with transaction.atomic():
        candidates = list(
            EventOutbox.objects.select_for_update(skip_locked=True)
            .filter(status__in=[DurableEventStatus.PENDING, DurableEventStatus.FAILED], available_at__lte=now)
            .order_by("created_at")[:limit]
        )
        for outbox in candidates:
            outbox.status = DurableEventStatus.PROCESSING
            outbox.lease_expires_at = lease_until
            outbox.attempts += 1
            outbox.save(update_fields=["status", "lease_expires_at", "attempts", "updated_at"])
            claimed.append(outbox)

    return claimed


def mark_outbox_published(outbox: EventOutbox) -> None:
    outbox.status = DurableEventStatus.PUBLISHED
    outbox.published_at = timezone.now()
    outbox.lease_expires_at = None
    outbox.last_error = ""
    outbox.save(update_fields=["status", "published_at", "lease_expires_at", "last_error", "updated_at"])


def mark_outbox_failed(outbox: EventOutbox, error_message: str, retry_delay_seconds: int = 30) -> None:
    outbox.status = DurableEventStatus.FAILED
    outbox.available_at = timezone.now() + timezone.timedelta(seconds=retry_delay_seconds)
    outbox.lease_expires_at = None
    outbox.last_error = error_message
    outbox.save(update_fields=["status", "available_at", "lease_expires_at", "last_error", "updated_at"])