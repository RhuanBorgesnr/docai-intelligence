"""
Email notification service for document expirations.
"""
import logging
from datetime import date
from typing import Optional

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from documents.models import Document, ExpirationNotification

logger = logging.getLogger(__name__)


def get_notification_type(days_until_expiration: int) -> Optional[str]:
    """Determine notification type based on days until expiration."""
    if days_until_expiration < 0:
        return ExpirationNotification.NotificationType.EXPIRED
    elif days_until_expiration <= 1:
        return ExpirationNotification.NotificationType.DAYS_1
    elif days_until_expiration <= 3:
        return ExpirationNotification.NotificationType.DAYS_3
    elif days_until_expiration <= 7:
        return ExpirationNotification.NotificationType.DAYS_7
    return None


def was_notification_sent(document: Document, notification_type: str, email: str) -> bool:
    """Check if this notification was already sent."""
    return ExpirationNotification.objects.filter(
        document=document,
        notification_type=notification_type,
        sent_to=email
    ).exists()


def record_notification(document: Document, notification_type: str, email: str) -> None:
    """Record that a notification was sent."""
    ExpirationNotification.objects.create(
        document=document,
        notification_type=notification_type,
        sent_to=email
    )


def send_expiration_email(
    document: Document,
    recipient_email: str,
    days_until_expiration: int,
    company_name: str = ""
) -> bool:
    """
    Send an expiration notification email.

    Returns True if email was sent successfully.
    """
    notification_type = get_notification_type(days_until_expiration)
    if not notification_type:
        return False

    # Skip if already sent
    if was_notification_sent(document, notification_type, recipient_email):
        logger.debug(
            "Notification %s already sent for doc %s to %s",
            notification_type, document.id, recipient_email
        )
        return False

    # Prepare email content
    doc_title = document.title or document.file.name.split('/')[-1]
    doc_type = document.get_document_type_display()

    if days_until_expiration < 0:
        subject = f"[VENCIDO] {doc_title}"
        urgency = "venceu"
        urgency_class = "expired"
    elif days_until_expiration <= 1:
        subject = f"[URGENTE] {doc_title} vence amanhã!"
        urgency = f"vence em {days_until_expiration} dia(s)"
        urgency_class = "urgent"
    elif days_until_expiration <= 3:
        subject = f"[ATENÇÃO] {doc_title} vence em {days_until_expiration} dias"
        urgency = f"vence em {days_until_expiration} dias"
        urgency_class = "warning"
    else:
        subject = f"[LEMBRETE] {doc_title} vence em {days_until_expiration} dias"
        urgency = f"vence em {days_until_expiration} dias"
        urgency_class = "info"

    # Build HTML email
    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #1e40af; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background: #f9fafb; }}
            .document-card {{ background: white; border-radius: 8px; padding: 20px; margin: 15px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            .badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
            .badge.expired {{ background: #fee2e2; color: #dc2626; }}
            .badge.urgent {{ background: #fef3c7; color: #d97706; }}
            .badge.warning {{ background: #fef9c3; color: #ca8a04; }}
            .badge.info {{ background: #dbeafe; color: #2563eb; }}
            .btn {{ display: inline-block; background: #1e40af; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin-top: 15px; }}
            .footer {{ text-align: center; padding: 20px; color: #6b7280; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Plataforma Inteligência</h1>
            </div>
            <div class="content">
                <h2>Alerta de Vencimento de Documento</h2>
                <p>Olá,</p>
                <p>Este é um lembrete sobre um documento que <strong>{urgency}</strong>:</p>

                <div class="document-card">
                    <h3>{doc_title}</h3>
                    <p><strong>Tipo:</strong> {doc_type}</p>
                    <p><strong>Vencimento:</strong> {document.expiration_date.strftime('%d/%m/%Y')}</p>
                    <p><strong>Empresa:</strong> {company_name or 'N/A'}</p>
                    <span class="badge {urgency_class}">{urgency.upper()}</span>
                </div>

                <p>Acesse a plataforma para mais detalhes e ações necessárias.</p>
            </div>
            <div class="footer">
                <p>Este é um email automático. Não responda.</p>
                <p>Plataforma Inteligência de Documentos</p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_message = strip_tags(html_message)

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            html_message=html_message,
            fail_silently=False,
        )
        record_notification(document, notification_type, recipient_email)
        logger.info("Sent expiration email for doc %s to %s", document.id, recipient_email)
        return True

    except Exception as e:
        logger.exception("Failed to send email for doc %s: %s", document.id, e)
        return False


def send_batch_expiration_email(
    documents: list,
    recipient_email: str,
    company_name: str = ""
) -> bool:
    """
    Send a single email with multiple expiring documents.
    """
    if not documents:
        return False

    today = date.today()

    # Build document rows
    doc_rows = ""
    for doc in documents:
        days = (doc.expiration_date - today).days
        doc_title = doc.title or doc.file.name.split('/')[-1]
        doc_type = doc.get_document_type_display()

        if days < 0:
            badge = '<span class="badge expired">VENCIDO</span>'
        elif days <= 1:
            badge = '<span class="badge urgent">URGENTE</span>'
        elif days <= 3:
            badge = '<span class="badge warning">ATENÇÃO</span>'
        else:
            badge = '<span class="badge info">LEMBRETE</span>'

        doc_rows += f"""
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{doc_title}</td>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{doc_type}</td>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{doc.expiration_date.strftime('%d/%m/%Y')}</td>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{badge}</td>
        </tr>
        """

    subject = f"[ALERTA] {len(documents)} documento(s) com vencimento próximo"

    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 700px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #1e40af; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background: #f9fafb; }}
            table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; }}
            th {{ background: #f3f4f6; padding: 12px; text-align: left; font-weight: 600; }}
            .badge {{ display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; }}
            .badge.expired {{ background: #fee2e2; color: #dc2626; }}
            .badge.urgent {{ background: #fef3c7; color: #d97706; }}
            .badge.warning {{ background: #fef9c3; color: #ca8a04; }}
            .badge.info {{ background: #dbeafe; color: #2563eb; }}
            .footer {{ text-align: center; padding: 20px; color: #6b7280; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Plataforma Inteligência</h1>
            </div>
            <div class="content">
                <h2>Resumo de Vencimentos</h2>
                <p>Olá,</p>
                <p>Você tem <strong>{len(documents)} documento(s)</strong> com vencimento próximo{f' na empresa {company_name}' if company_name else ''}:</p>

                <table>
                    <thead>
                        <tr>
                            <th>Documento</th>
                            <th>Tipo</th>
                            <th>Vencimento</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {doc_rows}
                    </tbody>
                </table>

                <p style="margin-top: 20px;">Acesse a plataforma para mais detalhes e ações necessárias.</p>
            </div>
            <div class="footer">
                <p>Este é um email automático. Não responda.</p>
                <p>Plataforma Inteligência de Documentos</p>
            </div>
        </div>
    </body>
    </html>
    """

    plain_message = strip_tags(html_message)

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info("Sent batch expiration email with %d docs to %s", len(documents), recipient_email)
        return True

    except Exception as e:
        logger.exception("Failed to send batch email: %s", e)
        return False
