"""
Email delivery channel via Django's mail subsystem.

Uses whatever ``EMAIL_BACKEND`` is configured in settings (console in dev,
SMTP in staging/production).

Supports:
- Plain text and HTML messages
- File attachments from notification context

Requires:
    EMAIL_BACKEND (defaults to console backend in dev)
    EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD for real SMTP
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone as dj_timezone

if TYPE_CHECKING:
    from notifications.models import Notification

logger = logging.getLogger(__name__)


def deliver(notification: Notification) -> tuple[bool, dict]:
    """
    Send *notification* via Django email backend.

    ``notification.recipient`` must be a valid email address.
    ``notification.subject`` is used as the email subject.
    ``notification.context`` may contain:
        - ``html_body``: HTML alternative body
        - ``attachments``: list of ``{filename, content, mimetype}`` dicts
    """
    from_email = getattr(
        settings,
        "DEFAULT_FROM_EMAIL",
        "Plataforma Inteligência <noreply@plataforma.com>",
    )
    to_email = notification.recipient
    subject = notification.subject or "Notificação"
    body = notification.message

    ctx = notification.context or {}

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[to_email],
        )

        # HTML alternative
        html_body = ctx.get("html_body")
        if html_body:
            msg.attach_alternative(html_body, "text/html")

        # Attachments
        for att in ctx.get("attachments", []):
            msg.attach(
                filename=att.get("filename", "attachment"),
                content=att.get("content", ""),
                mimetype=att.get("mimetype", "application/octet-stream"),
            )

        msg.send(fail_silently=False)

        logger.info(
            "[email] sent nid=%s to=%s subject=%r",
            notification.notification_id,
            to_email,
            subject,
        )
        return True, {
            "provider": "django_email",
            "to": to_email,
            "sent_at": dj_timezone.now().isoformat(),
        }

    except Exception as exc:
        logger.exception(
            "[email] delivery failed nid=%s to=%s: %s",
            notification.notification_id,
            to_email,
            exc,
        )
        return False, {"provider": "django_email", "error": str(exc)}
