"""
Telegram delivery channel via Bot API.

Uses ``python-telegram-bot`` (or falls back to raw ``requests``).

Supports:
- Plain text and Markdown messages
- Inline keyboards for approval actions

Requires env vars:
    TELEGRAM_BOT_TOKEN
    TELEGRAM_ENABLED=True   (default: False)
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone as dj_timezone

if TYPE_CHECKING:
    from notifications.models import Notification

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def _bot_token() -> str:
    return getattr(settings, "TELEGRAM_BOT_TOKEN", "")


def _is_enabled() -> bool:
    return (
        getattr(settings, "TELEGRAM_ENABLED", False)
        and bool(_bot_token())
    )


# ── low-level helpers (stdlib only, no extra deps) ─────────────────────────────

def _api_call(method: str, payload: dict) -> dict:
    """Call the Telegram Bot API and return the JSON response body."""
    token = _bot_token()
    url = f"{TELEGRAM_API}/bot{token}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _build_inline_keyboard(notification) -> list | None:
    """
    If the notification context contains ``approval_id`` build an
    inline keyboard with Approve / Reject buttons.
    """
    ctx = notification.context or {}
    approval_id = ctx.get("approval_id")
    if not approval_id:
        return None

    return [
        [
            {
                "text": "\u2705 Aprovar",
                "callback_data": json.dumps(
                    {"action": "approve", "approval_id": str(approval_id)}
                ),
            },
            {
                "text": "\u274c Rejeitar",
                "callback_data": json.dumps(
                    {"action": "reject", "approval_id": str(approval_id)}
                ),
            },
        ]
    ]


# ── public deliver function ────────────────────────────────────────────────────

def deliver(notification: Notification) -> tuple[bool, dict]:
    """
    Send *notification* via Telegram Bot API.

    ``notification.recipient`` must be a Telegram ``chat_id`` (numeric string).
    """
    if not _is_enabled():
        logger.info(
            "[telegram] disabled – stub delivery nid=%s to=%s",
            notification.notification_id,
            notification.recipient,
        )
        return True, {"provider": "stub_telegram", "reason": "disabled"}

    chat_id = notification.recipient
    text = notification.message
    if notification.subject:
        text = f"*{notification.subject}*\n\n{text}"

    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }

    keyboard = _build_inline_keyboard(notification)
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}

    try:
        result = _api_call("sendMessage", payload)
        message_id = result.get("result", {}).get("message_id")
        logger.info(
            "[telegram] sent nid=%s chat=%s msg_id=%s",
            notification.notification_id,
            chat_id,
            message_id,
        )
        return True, {
            "provider": "telegram_bot",
            "message_id": message_id,
            "chat_id": chat_id,
            "sent_at": dj_timezone.now().isoformat(),
        }

    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:500]
        logger.exception(
            "[telegram] HTTP %s nid=%s chat=%s: %s",
            exc.code,
            notification.notification_id,
            chat_id,
            body,
        )
        return False, {
            "provider": "telegram_bot",
            "error": f"HTTP {exc.code}: {body}",
        }
    except Exception as exc:
        logger.exception(
            "[telegram] delivery failed nid=%s chat=%s: %s",
            notification.notification_id,
            chat_id,
            exc,
        )
        return False, {"provider": "telegram_bot", "error": str(exc)}
