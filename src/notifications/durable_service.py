"""
Durable Notification Service.

Responsibilities:
- Persist every notification request before attempting delivery.
- Coordinate retries via DB state (no in-memory queues).
- Record every delivery attempt in an audit trail.
- Implement a simple channel-level circuit breaker via NotificationProviderHealth.
- Support fallback chain: primary channel → fallback channel → dead letter.
- Deduplicate via idempotency_key so callers can safely retry submission.
- Emit outbox events for downstream consumers (dashboard, webhooks, etc).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from asgiref.sync import async_to_sync, sync_to_async
from django.db import transaction
from django.utils import timezone as dj_timezone

from notifications.models import (
    Notification,
    NotificationDeliveryAttempt,
    NotificationProviderHealth,
)
from orchestrator.durable_events import persist_runtime_outbox_event
from orchestrator.enums import DurableNotificationStatus
from orchestrator.models import Case

logger = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────────────
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RESET_SECONDS = 60
MAX_RETRIES_DEFAULT = 3
RETRY_BASE_SECONDS = 5  # base for exponential backoff
LEASE_SECONDS = 30      # how long a worker holds a delivery slot


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_idempotency_key(notification_id: str, case_id: str) -> str:
    raw = f"{notification_id}:{case_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def _next_attempt_delta(attempt_number: int) -> timedelta:
    """Exponential back-off: 5, 10, 20, 40 … seconds."""
    return timedelta(seconds=RETRY_BASE_SECONDS * (2 ** attempt_number))


# ── circuit breaker helpers ────────────────────────────────────────────────────

def _get_or_create_health(channel: str) -> NotificationProviderHealth:
    obj, _ = NotificationProviderHealth.objects.get_or_create(
        channel=channel,
        defaults={
            "failure_threshold": CIRCUIT_FAILURE_THRESHOLD,
            "reset_after_seconds": CIRCUIT_RESET_SECONDS,
        },
    )
    return obj


def _circuit_is_open(channel: str) -> bool:
    """Returns True when the circuit is OPEN (provider unhealthy)."""
    try:
        health = NotificationProviderHealth.objects.get(channel=channel)
    except NotificationProviderHealth.DoesNotExist:
        return False

    if not health.is_open:
        return False

    # Auto-reset after cooldown
    if health.opened_at:
        age = (dj_timezone.now() - health.opened_at).total_seconds()
        if age >= health.reset_after_seconds:
            health.is_open = False
            health.failure_count = 0
            health.save(update_fields=["is_open", "failure_count", "updated_at"])
            return False

    return True


def _record_success(channel: str) -> None:
    health = _get_or_create_health(channel)
    health.success_count += 1
    health.last_success_at = dj_timezone.now()
    if health.is_open:
        health.is_open = False
        health.failure_count = 0
    health.save(update_fields=["success_count", "last_success_at", "is_open", "failure_count", "updated_at"])


def _record_failure(channel: str) -> None:
    health = _get_or_create_health(channel)
    health.failure_count += 1
    health.last_failure_at = dj_timezone.now()
    if health.failure_count >= health.failure_threshold and not health.is_open:
        health.is_open = True
        health.opened_at = dj_timezone.now()
        logger.warning(f"[notifications] Circuit OPENED for channel={channel}")
    health.save(update_fields=["failure_count", "last_failure_at", "is_open", "opened_at", "updated_at"])


# ── delivery backends (real channel implementations) ──────────────────────────

def _deliver_email(notification: Notification) -> tuple[bool, dict]:
    """Deliver via Django email backend (SMTP / console)."""
    from notifications.channels.email import deliver
    return deliver(notification)


def _deliver_whatsapp(notification: Notification) -> tuple[bool, dict]:
    """Deliver via Twilio WhatsApp API."""
    from notifications.channels.whatsapp import deliver
    return deliver(notification)


def _deliver_telegram(notification: Notification) -> tuple[bool, dict]:
    """Deliver via Telegram Bot API."""
    from notifications.channels.telegram import deliver
    return deliver(notification)


def _deliver_webhook(notification: Notification) -> tuple[bool, dict]:
    """Stub webhook delivery. Replace with httpx/requests."""
    import urllib.request
    payload = json.dumps(
        {
            "notification_id": notification.notification_id,
            "channel": notification.channel,
            "tenant_id": notification.tenant_id,
            "message": notification.message,
            "correlation_id": notification.correlation_id,
        }
    ).encode()
    try:
        req = urllib.request.Request(
            notification.recipient,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()[:512].decode(errors="replace")
        return True, {"status_code": resp.status, "body": body}
    except Exception as exc:  # noqa: BLE001
        return False, {"error": str(exc)}


def _deliver_log(notification: Notification) -> tuple[bool, dict]:
    logger.info(
        "[panel/log] nid=%s tenant=%s channel=%s recipient=%s message=%r",
        notification.notification_id,
        notification.tenant_id,
        notification.channel,
        notification.recipient,
        notification.message[:200],
    )
    return True, {"provider": "log"}


_BACKENDS: dict[str, Any] = {
    Notification.Channel.EMAIL: _deliver_email,
    Notification.Channel.WHATSAPP: _deliver_whatsapp,
    Notification.Channel.TELEGRAM: _deliver_telegram,
    Notification.Channel.WEBHOOK: _deliver_webhook,
    Notification.Channel.PANEL: _deliver_log,
    Notification.Channel.LOG: _deliver_log,
}


def _dispatch_channel(notification: Notification, channel: str) -> tuple[bool, dict, float]:
    """Attempt delivery via *channel*. Returns (success, provider_response, duration_ms)."""
    if _circuit_is_open(channel):
        return False, {"error": f"circuit_open:{channel}"}, 0.0

    backend = _BACKENDS.get(channel)
    if backend is None:
        return False, {"error": f"unknown_channel:{channel}"}, 0.0

    t0 = time.monotonic()
    try:
        ok, provider_resp = backend(notification)
        duration_ms = (time.monotonic() - t0) * 1000
        if ok:
            _record_success(channel)
        else:
            _record_failure(channel)
        return ok, provider_resp, duration_ms
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.monotonic() - t0) * 1000
        _record_failure(channel)
        return False, {"error": str(exc)}, duration_ms


# ── core service ──────────────────────────────────────────────────────────────

class DurableNotificationService:
    """
    Fully durable notification service backed by DB state.

    Usage (async):
        notif = await DurableNotificationService.submit(...)

    Usage (sync, e.g. from Celery):
        notif = DurableNotificationService.submit_sync(...)

    Retry sweep (called by Celery Beat):
        DurableNotificationService.retry_pending_sync(limit=50)
    """

    # ── submission ─────────────────────────────────────────────────────────────

    @classmethod
    def submit_sync(
        cls,
        notification_id: str,
        case_id: str,
        channel: str,
        recipient: str,
        message: str,
        tenant_id: str = "default",
        subject: str = "",
        correlation_id: str = "",
        trace_id: str = "",
        causation_id: str = "",
        template_name: str = "",
        context: Optional[dict] = None,
        max_retries: int = MAX_RETRIES_DEFAULT,
        fallback_channel: str = "",
        priority: str = Notification.Priority.NORMAL,
    ) -> Notification:
        """
        Persist a notification and attempt immediate delivery.

        Idempotent: calling twice with the same notification_id returns the
        existing record without re-sending.
        """
        idempotency_key = _build_idempotency_key(notification_id, case_id)

        # Idempotency: return existing record if already submitted
        existing = Notification.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            logger.debug(
                "[notifications] duplicate submission suppressed nid=%s", notification_id
            )
            return existing

        try:
            case = Case.objects.get(external_ref=case_id)
        except Case.DoesNotExist:
            raise ValueError(f"Case not found: {case_id}")

        with transaction.atomic():
            notif = Notification.objects.create(
                notification_id=notification_id,
                case=case,
                tenant_id=tenant_id,
                channel=channel,
                fallback_channel=fallback_channel,
                recipient=recipient,
                subject=subject,
                message=message,
                priority=priority,
                status=DurableNotificationStatus.PENDING,
                correlation_id=correlation_id,
                trace_id=trace_id,
                causation_id=causation_id,
                idempotency_key=idempotency_key,
                template_name=template_name,
                context=context or {},
                max_retries=max_retries,
            )

        logger.info(
            "[notifications] submitted nid=%s channel=%s tenant=%s",
            notification_id,
            channel,
            tenant_id,
        )

        # Attempt immediate delivery
        cls._attempt_delivery_sync(notif)
        return notif

    @classmethod
    async def submit(cls, **kwargs) -> Notification:
        return await sync_to_async(cls.submit_sync)(**kwargs)

    # ── delivery attempt ───────────────────────────────────────────────────────

    @classmethod
    def _attempt_delivery_sync(cls, notif: Notification) -> bool:
        """
        Try to deliver *notif*. Returns True on success.
        Handles circuit-breaker, fallback, retry scheduling, and dead-letter.
        """
        now = dj_timezone.now()

        # Claim a delivery slot via lease
        with transaction.atomic():
            locked = (
                Notification.objects.select_for_update(skip_locked=True)
                .filter(pk=notif.pk, is_dead=False)
                .exclude(status=DurableNotificationStatus.SENT)
                .first()
            )
            if locked is None:
                return False  # already delivered or locked by another worker

            locked.status = DurableNotificationStatus.DISPATCHING
            locked.leased_until = now + timedelta(seconds=LEASE_SECONDS)
            locked.save(update_fields=["status", "leased_until", "updated_at"])

        attempt_number = locked.attempts + 1
        t_start = dj_timezone.now()

        # Primary channel attempt
        primary_channel = locked.channel
        ok, provider_resp, duration_ms = _dispatch_channel(locked, primary_channel)

        if not ok and locked.fallback_channel:
            fallback_channel = locked.fallback_channel
            logger.warning(
                "[notifications] primary failed, trying fallback nid=%s primary=%s fallback=%s",
                locked.notification_id,
                primary_channel,
                fallback_channel,
            )
            ok2, provider_resp2, duration_ms2 = _dispatch_channel(locked, fallback_channel)
            if ok2:
                ok = True
                provider_resp = {**provider_resp2, "via_fallback": True}
                duration_ms = duration_ms2
                primary_channel = fallback_channel  # record which channel actually succeeded

        t_end = dj_timezone.now()

        # Write audit attempt
        NotificationDeliveryAttempt.objects.create(
            notification=locked,
            attempt_number=attempt_number,
            channel=primary_channel,
            recipient=locked.recipient,
            outcome=(
                NotificationDeliveryAttempt.Outcome.SUCCESS
                if ok
                else NotificationDeliveryAttempt.Outcome.FAILURE
            ),
            error="" if ok else provider_resp.get("error", ""),
            provider_response=provider_resp,
            duration_ms=duration_ms,
            started_at=t_start,
            finished_at=t_end,
        )

        with transaction.atomic():
            locked.attempts = attempt_number
            locked.provider_response = provider_resp

            if ok:
                locked.status = DurableNotificationStatus.SENT
                locked.sent_at = dj_timezone.now()
                locked.leased_until = None
                locked.error_message = ""
            else:
                if attempt_number >= locked.max_retries:
                    locked.status = DurableNotificationStatus.FAILED
                    locked.is_dead = True
                    locked.leased_until = None
                    locked.error_message = provider_resp.get("error", "delivery_failed")
                    logger.error(
                        "[notifications] dead-lettered nid=%s after %d attempts",
                        locked.notification_id,
                        attempt_number,
                    )
                    cls._emit_event_sync(locked, "notification.dead_lettered")
                else:
                    locked.status = DurableNotificationStatus.FAILED
                    locked.leased_until = None
                    locked.next_attempt_at = dj_timezone.now() + _next_attempt_delta(attempt_number)
                    locked.error_message = provider_resp.get("error", "delivery_failed")

            locked.save(
                update_fields=[
                    "attempts",
                    "provider_response",
                    "status",
                    "sent_at",
                    "leased_until",
                    "next_attempt_at",
                    "error_message",
                    "is_dead",
                    "updated_at",
                ]
            )

        if ok:
            cls._emit_event_sync(locked, "notification.sent")

        return ok

    # ── retry sweep ────────────────────────────────────────────────────────────

    @classmethod
    def retry_pending_sync(cls, limit: int = 50) -> dict:
        """
        Pick up due notifications and retry delivery.
        Called by Celery Beat every 30 seconds.
        """
        now = dj_timezone.now()
        due = (
            Notification.objects.filter(
                status__in=[DurableNotificationStatus.FAILED, DurableNotificationStatus.PENDING],
                is_dead=False,
                next_attempt_at__lte=now,
            )
            .exclude(leased_until__gt=now)
            .order_by("next_attempt_at")[:limit]
        )

        results = {"retried": 0, "succeeded": 0, "failed": 0}
        for notif in due:
            results["retried"] += 1
            ok = cls._attempt_delivery_sync(notif)
            if ok:
                results["succeeded"] += 1
            else:
                results["failed"] += 1

        if results["retried"]:
            logger.info("[notifications] retry_sweep results=%s", results)
        return results

    # ── outbox event ──────────────────────────────────────────────────────────

    @classmethod
    def _emit_event_sync(cls, notif: Notification, event_type: str) -> None:
        try:
            persist_runtime_outbox_event(
                event_id=f"{event_type}:{notif.notification_id}",
                case=notif.case,
                event_type=event_type,
                source="notification_service",
                tenant_id=notif.tenant_id,
                correlation_id=notif.correlation_id,
                trace_id=notif.trace_id,
                payload={
                    "notification_id": notif.notification_id,
                    "channel": notif.channel,
                    "recipient": notif.recipient,
                    "attempts": notif.attempts,
                    "status": notif.status,
                },
                causation_id=notif.causation_id or notif.notification_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "[notifications] failed to emit outbox event for nid=%s", notif.notification_id
            )

    # ── query helpers ─────────────────────────────────────────────────────────

    @classmethod
    def get_notification(cls, notification_id: str) -> Optional[Notification]:
        return Notification.objects.filter(notification_id=notification_id).first()

    @classmethod
    def list_for_case(cls, case_id: str) -> list[Notification]:
        return list(
            Notification.objects.filter(case__external_ref=case_id).order_by("-created_at")
        )

    @classmethod
    def provider_health(cls) -> list[dict]:
        return [
            {
                "channel": h.channel,
                "is_open": h.is_open,
                "failure_count": h.failure_count,
                "success_count": h.success_count,
                "last_failure_at": h.last_failure_at,
                "last_success_at": h.last_success_at,
            }
            for h in NotificationProviderHealth.objects.all()
        ]
