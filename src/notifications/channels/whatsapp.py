"""
WhatsApp delivery channel via Twilio API.

Uses the existing Twilio client from ``documents.whatsapp`` but integrates
with the durable notification pipeline (circuit breaker, rate limiter).

Requires env vars:
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_WHATSAPP_FROM   (e.g. ``whatsapp:+14155238886``)
    WHATSAPP_ENABLED=True
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone as dj_timezone

if TYPE_CHECKING:
    from notifications.models import Notification

logger = logging.getLogger(__name__)

# ── Twilio client (lazy, optional) ─────────────────────────────────────────────

_twilio_client = None

try:
    from twilio.rest import Client as TwilioClient

    TWILIO_AVAILABLE = True
except ImportError:
    TwilioClient = None  # type: ignore[assignment,misc]
    TWILIO_AVAILABLE = False


def _get_client():
    global _twilio_client
    if _twilio_client is not None:
        return _twilio_client

    sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
    token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
    if not sid or not token or not TWILIO_AVAILABLE:
        return None

    _twilio_client = TwilioClient(sid, token)
    return _twilio_client


def _format_whatsapp_number(phone: str) -> str:
    """Normalise a phone string to ``whatsapp:+<digits>``."""
    if phone.startswith("whatsapp:"):
        return phone
    clean = "".join(c for c in phone if c.isdigit())
    if len(clean) == 11:          # BR mobile DDD+9digits
        clean = "55" + clean
    elif len(clean) == 10:        # BR old format
        clean = "55" + clean
    return f"whatsapp:+{clean}"


# ── public deliver function ────────────────────────────────────────────────────

def deliver(notification: Notification) -> tuple[bool, dict]:
    """
    Send *notification* via WhatsApp/Twilio.

    Returns ``(True, {sid, ...})`` on success, ``(False, {error})`` on failure.
    Falls back to a log-only stub when Twilio is not configured.
    """
    enabled = getattr(settings, "WHATSAPP_ENABLED", False)
    if not enabled:
        logger.info(
            "[whatsapp] disabled – stub delivery nid=%s to=%s",
            notification.notification_id,
            notification.recipient,
        )
        return True, {"provider": "stub_whatsapp", "reason": "disabled"}

    client = _get_client()
    if client is None:
        logger.warning("[whatsapp] Twilio client unavailable, stub delivery")
        return True, {"provider": "stub_whatsapp", "reason": "no_client"}

    from_number = getattr(settings, "TWILIO_WHATSAPP_FROM", "")
    to_number = _format_whatsapp_number(notification.recipient)

    body = notification.message
    if notification.subject:
        body = f"*{notification.subject}*\n\n{body}"

    # Optionally attach media from context
    media_url: list[str] = []
    ctx = notification.context or {}
    if ctx.get("media_url"):
        media_url = [ctx["media_url"]] if isinstance(ctx["media_url"], str) else ctx["media_url"]

    try:
        kwargs: dict = {
            "body": body,
            "from_": from_number,
            "to": to_number,
        }
        if media_url:
            kwargs["media_url"] = media_url

        msg = client.messages.create(**kwargs)

        logger.info(
            "[whatsapp] sent nid=%s sid=%s to=%s",
            notification.notification_id,
            msg.sid,
            to_number,
        )
        return True, {
            "provider": "twilio_whatsapp",
            "sid": msg.sid,
            "status": msg.status,
            "sent_at": dj_timezone.now().isoformat(),
        }

    except Exception as exc:
        logger.exception(
            "[whatsapp] delivery failed nid=%s to=%s: %s",
            notification.notification_id,
            to_number,
            exc,
        )
        return False, {"provider": "twilio_whatsapp", "error": str(exc)}
