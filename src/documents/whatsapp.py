"""
WhatsApp notification service using Twilio API.
"""
import logging
from datetime import date
from typing import List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Try to import twilio, but make it optional
try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    logger.warning("Twilio not installed. WhatsApp notifications disabled.")


def is_whatsapp_enabled() -> bool:
    """Check if WhatsApp notifications are enabled and configured."""
    if not TWILIO_AVAILABLE:
        return False

    return (
        getattr(settings, 'WHATSAPP_ENABLED', False) and
        getattr(settings, 'TWILIO_ACCOUNT_SID', '') and
        getattr(settings, 'TWILIO_AUTH_TOKEN', '')
    )


def get_twilio_client():
    """Get configured Twilio client."""
    if not TWILIO_AVAILABLE:
        return None

    account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
    auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')

    if not account_sid or not auth_token:
        return None

    return Client(account_sid, auth_token)


def format_whatsapp_number(phone: str) -> str:
    """Format phone number for WhatsApp."""
    # Remove non-numeric characters
    clean = ''.join(c for c in phone if c.isdigit())

    # Add Brazil country code if not present
    if len(clean) == 11:  # Brazilian mobile: DDD + 9 digits
        clean = '55' + clean
    elif len(clean) == 10:  # Old format without 9
        clean = '55' + clean

    return f"whatsapp:+{clean}"


def send_whatsapp_message(to_phone: str, message: str) -> bool:
    """
    Send a WhatsApp message via Twilio.

    Args:
        to_phone: Recipient phone number (will be formatted).
        message: Message text to send.

    Returns:
        True if sent successfully.
    """
    if not is_whatsapp_enabled():
        logger.info("WhatsApp disabled, would send to %s: %s", to_phone, message[:50])
        return False

    client = get_twilio_client()
    if not client:
        logger.warning("Twilio client not available")
        return False

    from_number = getattr(settings, 'TWILIO_WHATSAPP_FROM', '')
    to_number = format_whatsapp_number(to_phone)

    try:
        msg = client.messages.create(
            body=message,
            from_=from_number,
            to=to_number
        )
        logger.info("WhatsApp sent to %s, SID: %s", to_phone, msg.sid)
        return True

    except Exception as e:
        logger.exception("Failed to send WhatsApp to %s: %s", to_phone, e)
        return False


def send_expiration_whatsapp(
    to_phone: str,
    doc_title: str,
    days_until_expiration: int,
    expiration_date: date,
    company_name: str = ""
) -> bool:
    """
    Send an expiration alert via WhatsApp.
    """
    if days_until_expiration < 0:
        urgency = "⚠️ *VENCIDO*"
    elif days_until_expiration <= 1:
        urgency = "🔴 *URGENTE*"
    elif days_until_expiration <= 3:
        urgency = "🟠 *ATENÇÃO*"
    else:
        urgency = "🟡 *LEMBRETE*"

    message = f"""
{urgency}

📄 *Documento:* {doc_title}
📅 *Vencimento:* {expiration_date.strftime('%d/%m/%Y')}
⏰ *Dias restantes:* {days_until_expiration if days_until_expiration >= 0 else 'Vencido'}
{f'🏢 *Empresa:* {company_name}' if company_name else ''}

Acesse a plataforma para mais detalhes.

_Plataforma Inteligência de Documentos_
""".strip()

    return send_whatsapp_message(to_phone, message)


def send_batch_expiration_whatsapp(
    to_phone: str,
    documents: List[dict],
    company_name: str = ""
) -> bool:
    """
    Send a batch expiration summary via WhatsApp.

    Args:
        to_phone: Recipient phone number.
        documents: List of dicts with 'title', 'expiration_date', 'days_left'.
        company_name: Optional company name.
    """
    if not documents:
        return False

    # Count by urgency
    urgent = sum(1 for d in documents if d.get('days_left', 99) <= 3)

    doc_list = ""
    for doc in documents[:5]:  # Limit to 5 docs in message
        days = doc.get('days_left', 0)
        if days < 0:
            emoji = "🔴"
        elif days <= 3:
            emoji = "🟠"
        else:
            emoji = "🟡"

        doc_list += f"\n{emoji} {doc['title'][:30]} - {doc['expiration_date']}"

    if len(documents) > 5:
        doc_list += f"\n_...e mais {len(documents) - 5} documento(s)_"

    message = f"""
⚠️ *ALERTA DE VENCIMENTOS*

Você tem *{len(documents)} documento(s)* com vencimento próximo{f' em {company_name}' if company_name else ''}:
{doc_list}

{'🔴 *' + str(urgent) + ' urgente(s)!*' if urgent > 0 else ''}

Acesse a plataforma para mais detalhes.

_Plataforma Inteligência de Documentos_
""".strip()

    return send_whatsapp_message(to_phone, message)


def send_financial_summary_whatsapp(
    to_phone: str,
    indicators: dict,
    period: str = "",
    company_name: str = ""
) -> bool:
    """
    Send financial indicators summary via WhatsApp.
    """
    def fmt(value):
        if value is None:
            return "-"
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    receita = indicators.get('receita_liquida')
    lucro = indicators.get('lucro_liquido')
    ebitda = indicators.get('ebitda')
    margem = indicators.get('margem_liquida')

    message = f"""
📊 *RESUMO FINANCEIRO*
{f'📅 Período: {period}' if period else ''}
{f'🏢 Empresa: {company_name}' if company_name else ''}

💰 *Receita Líquida:* {fmt(receita)}
📈 *Lucro Líquido:* {fmt(lucro)}
📊 *EBITDA:* {fmt(ebitda)}
📉 *Margem Líquida:* {f'{margem:.1f}%' if margem else '-'}

_Plataforma Inteligência de Documentos_
""".strip()

    return send_whatsapp_message(to_phone, message)
