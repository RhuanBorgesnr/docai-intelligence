"""
Real Email Sender — sends actual emails via Django's email backend.

Replaces the mock in NotificationService._send_email for production use.
Uses Django's EMAIL_* settings (SMTP, console, or any backend).

Also handles:
- WhatsApp link generation (wa.me deep links)
- Follow-up dispatch after approval

Sprint 4 / Operational Phase.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

logger = logging.getLogger(__name__)


# ── Real Email ────────────────────────────────────────────────────────────────

def send_real_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    from_email: str | None = None,
    reply_to: str | None = None,
) -> bool:
    """
    Send a real email using Django's configured email backend.
    In dev: prints to console (ConsoleEmailBackend).
    In prod: sends via SMTP (set EMAIL_BACKEND + EMAIL_HOST_* env vars).
    """
    try:
        from_addr = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@docai.ai")
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body_text,
            from_email=from_addr,
            to=[to] if isinstance(to, str) else to,
            reply_to=[reply_to] if reply_to else None,
        )
        if body_html:
            msg.attach_alternative(body_html, "text/html")
        msg.send(fail_silently=False)
        logger.info("[EMAIL] Sent to=%s subject='%s'", to, subject)
        return True
    except Exception as exc:
        logger.error("[EMAIL] Failed to=%s: %s", to, exc)
        return False


# ── WhatsApp Link ─────────────────────────────────────────────────────────────

def whatsapp_link(phone: str, message: str = "") -> str:
    """
    Generate a wa.me deep link for WhatsApp.
    Phone should be in international format (e.g., 5511999998888).
    """
    clean_phone = "".join(c for c in phone if c.isdigit())
    if not clean_phone.startswith("55") and len(clean_phone) <= 11:
        clean_phone = "55" + clean_phone
    url = f"https://wa.me/{clean_phone}"
    if message:
        url += f"?text={quote(message)}"
    return url


# ── Follow-up Dispatch (after approval) ──────────────────────────────────────

def dispatch_approved_followup(draft_id: str) -> dict[str, Any]:
    """
    Actually send a follow-up that was approved.
    Called after the operator approves in /ops/approvals.

    Flow:
    1. Load the FollowUpDraft
    2. Send via the draft's channel (email or whatsapp link)
    3. Update draft status to SENT
    4. Create audit trail
    5. Return result
    """
    from commercial.models import FollowUpDraft
    from audit.models import AuditLog

    try:
        draft = FollowUpDraft.objects.select_related("lead").get(draft_id=draft_id)
    except FollowUpDraft.DoesNotExist:
        return {"error": f"Draft {draft_id} not found", "sent": False}

    if draft.status not in (FollowUpDraft.Status.APPROVED, FollowUpDraft.Status.PENDING_APPROVAL):
        return {"error": f"Draft status is {draft.status}, cannot send", "sent": False}

    lead = draft.lead
    result = {"draft_id": draft_id, "channel": draft.channel, "lead_id": lead.lead_id}

    if draft.channel == FollowUpDraft.Channel.EMAIL:
        if not lead.contact_email:
            result["error"] = "Lead has no email"
            result["sent"] = False
            return result

        body_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px;">
            <p>{draft.body.replace(chr(10), '<br>')}</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="color: #999; font-size: 11px;">
                Enviado via DocAI · {lead.company_name or ''}
            </p>
        </div>
        """
        sent = send_real_email(
            to=lead.contact_email,
            subject=draft.subject or "DocAI — Follow-up",
            body_text=draft.body,
            body_html=body_html,
        )
        result["sent"] = sent
        result["recipient"] = lead.contact_email

    elif draft.channel == FollowUpDraft.Channel.WHATSAPP:
        if not lead.contact_phone:
            result["error"] = "Lead has no phone"
            result["sent"] = False
            return result

        link = whatsapp_link(lead.contact_phone, draft.body[:500])
        result["sent"] = True  # Link generated, human will click
        result["whatsapp_link"] = link
        result["recipient"] = lead.contact_phone

    else:
        result["error"] = f"Unsupported channel: {draft.channel}"
        result["sent"] = False
        return result

    # Update draft status
    if result.get("sent"):
        draft.status = FollowUpDraft.Status.SENT
        draft.sent_at = timezone.now()
        draft.save(update_fields=["status", "sent_at", "updated_at"])

        # Update lead activity
        lead.last_event_at = timezone.now()
        lead.save(update_fields=["last_event_at", "updated_at"])

        # Audit
        AuditLog.objects.create(
            action="followup.sent",
            actor_type="system",
            actor_id="dispatch",
            details={
                "draft_id": draft_id,
                "channel": draft.channel,
                "lead_id": lead.lead_id,
                "recipient": result.get("recipient", ""),
            },
        )

    return result
