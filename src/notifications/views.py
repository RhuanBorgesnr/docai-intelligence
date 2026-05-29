"""
Webhook endpoints for notification channel callbacks.

- ``POST /webhooks/whatsapp/status/``  — Twilio status callback
- ``POST /webhooks/telegram/``         — Telegram Bot update (callback queries)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


# ── WhatsApp / Twilio status callback ──────────────────────────────────────────

def _verify_twilio_signature(request) -> bool:
    """
    Validate the ``X-Twilio-Signature`` header.
    Returns True when verification is disabled (no auth token) or when valid.
    """
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
    if not auth_token:
        return True  # skip verification when no token configured (dev)

    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(auth_token)
        url = request.build_absolute_uri()
        params = request.POST.dict()
        signature = request.META.get("HTTP_X_TWILIO_SIGNATURE", "")
        return validator.validate(url, params, signature)
    except ImportError:
        return True  # twilio package not installed — skip validation


@csrf_exempt
@require_POST
def whatsapp_status_callback(request):
    """
    Receive delivery status updates from Twilio (``StatusCallback``).

    Twilio POSTs form-encoded data with fields:
    ``MessageSid``, ``MessageStatus``, ``To``, ``From``, ``ErrorCode``, etc.
    """
    if not _verify_twilio_signature(request):
        logger.warning("[webhook:whatsapp] invalid Twilio signature")
        return HttpResponse(status=403)

    message_sid = request.POST.get("MessageSid", "")
    status = request.POST.get("MessageStatus", "")
    error_code = request.POST.get("ErrorCode", "")
    to = request.POST.get("To", "")

    logger.info(
        "[webhook:whatsapp] status=%s sid=%s to=%s error=%s",
        status,
        message_sid,
        to,
        error_code,
    )

    # Update notification record if we can find it by SID
    from notifications.models import Notification

    notif = Notification.objects.filter(
        provider_response__sid=message_sid,
    ).first()

    if notif:
        notif.provider_response = {
            **(notif.provider_response or {}),
            "delivery_status": status,
            "error_code": error_code,
        }
        notif.save(update_fields=["provider_response", "updated_at"])

    # Twilio expects a 200 with optional TwiML — empty is fine
    return HttpResponse(status=200, content_type="text/xml")


# ── Telegram callback query handler ───────────────────────────────────────────

@csrf_exempt
@require_POST
def telegram_webhook(request):
    """
    Receive updates from Telegram Bot API (via configured webhook).

    Handles ``callback_query`` updates for approval inline keyboards.
    Other update types are acknowledged but not processed.
    """
    try:
        update = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "invalid_json"}, status=400)

    # Callback query — user clicked an inline keyboard button
    callback_query = update.get("callback_query")
    if callback_query:
        return _handle_callback_query(callback_query)

    # Other updates (messages, etc.) — just acknowledge
    return JsonResponse({"ok": True})


def _handle_callback_query(callback_query: dict) -> JsonResponse:
    """Process an approval callback from a Telegram inline keyboard."""
    query_id = callback_query.get("id", "")
    data_raw = callback_query.get("data", "")
    user = callback_query.get("from", {})
    chat_id = callback_query.get("message", {}).get("chat", {}).get("id")

    try:
        data = json.loads(data_raw)
    except (json.JSONDecodeError, ValueError):
        _answer_callback(query_id, "Dados inválidos")
        return JsonResponse({"ok": False, "error": "bad_callback_data"})

    action = data.get("action")
    approval_id = data.get("approval_id")

    if not action or not approval_id:
        _answer_callback(query_id, "Dados incompletos")
        return JsonResponse({"ok": False, "error": "missing_fields"})

    logger.info(
        "[webhook:telegram] callback action=%s approval_id=%s user=%s chat=%s",
        action,
        approval_id,
        user.get("id"),
        chat_id,
    )

    # Dispatch to approval gateway
    try:
        from approvals.gateway import ApprovalGateway

        decision = "approved" if action == "approve" else "rejected"
        decided_by = f"telegram:{user.get('id', 'unknown')}"
        notes = f"Via Telegram by {user.get('first_name', '')} {user.get('last_name', '')}".strip()

        result = ApprovalGateway.decide_approval(
            approval_id=approval_id,
            decision=decision,
            decided_by=decided_by,
            notes=notes,
        )

        emoji = "\u2705" if decision == "approved" else "\u274c"
        _answer_callback(query_id, f"{emoji} {decision.capitalize()}")
        _edit_message_text(
            chat_id,
            callback_query["message"]["message_id"],
            f"{emoji} Aprovação {decision} por {user.get('first_name', '')}",
        )

        return JsonResponse({"ok": True, "decision": decision})

    except Exception as exc:
        logger.exception("[webhook:telegram] approval error: %s", exc)
        _answer_callback(query_id, f"Erro: {exc}")
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)


# ── Telegram API helpers ───────────────────────────────────────────────────────

def _answer_callback(callback_query_id: str, text: str) -> None:
    """Send ``answerCallbackQuery`` to dismiss the loading spinner."""
    try:
        from notifications.channels.telegram import _api_call
        _api_call("answerCallbackQuery", {
            "callback_query_id": callback_query_id,
            "text": text,
        })
    except Exception:
        logger.debug("[webhook:telegram] failed to answer callback query", exc_info=True)


def _edit_message_text(chat_id, message_id: int, text: str) -> None:
    """Edit the original message to show the decision result."""
    try:
        from notifications.channels.telegram import _api_call
        _api_call("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        })
    except Exception:
        logger.debug("[webhook:telegram] failed to edit message", exc_info=True)
