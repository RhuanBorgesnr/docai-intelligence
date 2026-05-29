"""
Sprint 3 – Bloco 1: Notification Providers Integration Tests.

Tests real channel backends (WhatsApp, Telegram, Email) with mocked external APIs,
plus fallback chain, circuit breaker integration, and webhook handlers.
"""

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory
from django.utils import timezone as dj_timezone

from notifications.durable_service import (
    DurableNotificationService,
    _circuit_is_open,
    _record_failure,
    _record_success,
)
from notifications.models import (
    Notification,
    NotificationDeliveryAttempt,
    NotificationProviderHealth,
)
from orchestrator.enums import DurableNotificationStatus
from orchestrator.models import Case


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_case(ref: str = "case-sprint3-notif") -> Case:
    return Case.objects.create(
        external_ref=ref,
        tenant_id="tenant-sprint3",
        title="Sprint 3 notification test",
        correlation_id=f"corr-{ref}",
        trace_id=f"trace-{ref}",
    )


# ══════════════════════════════════════════════════════════════════════════════
#  WhatsApp Channel
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_whatsapp_deliver_stub_when_disabled():
    """WhatsApp returns stub success when WHATSAPP_ENABLED=False."""
    from notifications.channels.whatsapp import deliver

    notif = MagicMock()
    notif.notification_id = "nid-wa-stub"
    notif.recipient = "+5511999999999"
    notif.message = "Hello"
    notif.subject = ""
    notif.context = {}

    with patch("notifications.channels.whatsapp.settings") as mock_settings:
        mock_settings.WHATSAPP_ENABLED = False
        ok, resp = deliver(notif)

    assert ok is True
    assert resp["provider"] == "stub_whatsapp"
    assert resp["reason"] == "disabled"


@pytest.mark.django_db(transaction=True)
def test_whatsapp_deliver_real_twilio_mock():
    """WhatsApp sends via Twilio when enabled (mocked client)."""
    from notifications.channels.whatsapp import deliver

    notif = MagicMock()
    notif.notification_id = "nid-wa-real"
    notif.recipient = "+5511999999999"
    notif.message = "Proposta aprovada"
    notif.subject = "Aprovação"
    notif.context = {}

    mock_msg = MagicMock()
    mock_msg.sid = "SM_test_sid_123"
    mock_msg.status = "queued"

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch("notifications.channels.whatsapp.settings") as mock_settings, \
         patch("notifications.channels.whatsapp._get_client", return_value=mock_client):
        mock_settings.WHATSAPP_ENABLED = True
        mock_settings.TWILIO_WHATSAPP_FROM = "whatsapp:+14155238886"

        ok, resp = deliver(notif)

    assert ok is True
    assert resp["provider"] == "twilio_whatsapp"
    assert resp["sid"] == "SM_test_sid_123"
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args[1]
    assert "Aprovação" in call_kwargs["body"]


@pytest.mark.django_db(transaction=True)
def test_whatsapp_deliver_with_media():
    """WhatsApp passes media_url from notification context."""
    from notifications.channels.whatsapp import deliver

    notif = MagicMock()
    notif.notification_id = "nid-wa-media"
    notif.recipient = "+5511999999999"
    notif.message = "Proposta em anexo"
    notif.subject = ""
    notif.context = {"media_url": "https://example.com/proposta.pdf"}

    mock_msg = MagicMock(sid="SM_media", status="queued")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch("notifications.channels.whatsapp.settings") as mock_settings, \
         patch("notifications.channels.whatsapp._get_client", return_value=mock_client):
        mock_settings.WHATSAPP_ENABLED = True
        mock_settings.TWILIO_WHATSAPP_FROM = "whatsapp:+14155238886"

        ok, resp = deliver(notif)

    assert ok is True
    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["media_url"] == ["https://example.com/proposta.pdf"]


# ══════════════════════════════════════════════════════════════════════════════
#  Telegram Channel
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_telegram_deliver_stub_when_disabled():
    """Telegram returns stub success when TELEGRAM_ENABLED=False."""
    from notifications.channels.telegram import deliver

    notif = MagicMock()
    notif.notification_id = "nid-tg-stub"
    notif.recipient = "123456789"
    notif.message = "Test"
    notif.subject = ""
    notif.context = {}

    with patch("notifications.channels.telegram.settings") as mock_settings:
        mock_settings.TELEGRAM_ENABLED = False
        mock_settings.TELEGRAM_BOT_TOKEN = ""
        ok, resp = deliver(notif)

    assert ok is True
    assert resp["provider"] == "stub_telegram"


@pytest.mark.django_db(transaction=True)
def test_telegram_deliver_with_api_mock():
    """Telegram sends via Bot API when enabled (mocked HTTP)."""
    from notifications.channels.telegram import deliver

    notif = MagicMock()
    notif.notification_id = "nid-tg-real"
    notif.recipient = "123456789"
    notif.message = "Novo lead qualificado"
    notif.subject = "Lead"
    notif.context = {}

    api_response = {"ok": True, "result": {"message_id": 42}}

    with patch("notifications.channels.telegram.settings") as mock_settings, \
         patch("notifications.channels.telegram._api_call", return_value=api_response) as mock_api:
        mock_settings.TELEGRAM_ENABLED = True
        mock_settings.TELEGRAM_BOT_TOKEN = "test-token"

        ok, resp = deliver(notif)

    assert ok is True
    assert resp["provider"] == "telegram_bot"
    assert resp["message_id"] == 42
    mock_api.assert_called_once_with("sendMessage", {
        "chat_id": "123456789",
        "text": "*Lead*\n\nNovo lead qualificado",
        "parse_mode": "Markdown",
    })


@pytest.mark.django_db(transaction=True)
def test_telegram_deliver_with_approval_keyboard():
    """Telegram builds inline keyboard when approval_id is in context."""
    from notifications.channels.telegram import deliver

    notif = MagicMock()
    notif.notification_id = "nid-tg-approval"
    notif.recipient = "123456789"
    notif.message = "Aprovar proposta R$10.000?"
    notif.subject = ""
    notif.context = {"approval_id": "apv-001"}

    api_response = {"ok": True, "result": {"message_id": 99}}

    with patch("notifications.channels.telegram.settings") as mock_settings, \
         patch("notifications.channels.telegram._api_call", return_value=api_response) as mock_api:
        mock_settings.TELEGRAM_ENABLED = True
        mock_settings.TELEGRAM_BOT_TOKEN = "test-token"

        ok, resp = deliver(notif)

    assert ok is True
    call_args = mock_api.call_args[0]
    payload = call_args[1]
    assert "reply_markup" in payload
    keyboard = payload["reply_markup"]["inline_keyboard"]
    assert len(keyboard) == 1  # one row
    assert len(keyboard[0]) == 2  # two buttons
    assert "approve" in keyboard[0][0]["callback_data"]
    assert "reject" in keyboard[0][1]["callback_data"]


# ══════════════════════════════════════════════════════════════════════════════
#  Email Channel
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_email_deliver_success():
    """Email sends via Django mail backend."""
    from notifications.channels.email import deliver

    notif = MagicMock()
    notif.notification_id = "nid-email-1"
    notif.recipient = "user@example.com"
    notif.message = "Sua proposta foi aprovada"
    notif.subject = "Aprovação"
    notif.context = {}

    with patch("notifications.channels.email.EmailMultiAlternatives") as MockEmail:
        instance = MockEmail.return_value
        instance.send.return_value = 1

        ok, resp = deliver(notif)

    assert ok is True
    assert resp["provider"] == "django_email"
    MockEmail.assert_called_once()
    instance.send.assert_called_once_with(fail_silently=False)


@pytest.mark.django_db(transaction=True)
def test_email_deliver_with_html_and_attachments():
    """Email supports HTML body and file attachments."""
    from notifications.channels.email import deliver

    notif = MagicMock()
    notif.notification_id = "nid-email-html"
    notif.recipient = "user@example.com"
    notif.message = "Texto plano"
    notif.subject = "Relatório"
    notif.context = {
        "html_body": "<h1>Relatório</h1><p>Dados aqui</p>",
        "attachments": [
            {"filename": "report.pdf", "content": b"PDF", "mimetype": "application/pdf"}
        ],
    }

    with patch("notifications.channels.email.EmailMultiAlternatives") as MockEmail:
        instance = MockEmail.return_value
        instance.send.return_value = 1

        ok, resp = deliver(notif)

    assert ok is True
    instance.attach_alternative.assert_called_once()
    instance.attach.assert_called_once_with(
        filename="report.pdf",
        content=b"PDF",
        mimetype="application/pdf",
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Durable Pipeline – Fallback Chain
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_fallback_whatsapp_to_telegram():
    """When WhatsApp fails, notification falls back to Telegram."""
    case = _make_case("case-fallback-1")

    with patch("notifications.channels.whatsapp.deliver") as mock_wa, \
         patch("notifications.channels.telegram.deliver") as mock_tg:
        mock_wa.return_value = (False, {"error": "twilio_down"})
        mock_tg.return_value = (True, {"provider": "telegram_bot", "message_id": 55})

        notif = DurableNotificationService.submit_sync(
            notification_id="nid-fallback-1",
            case_id="case-fallback-1",
            channel=Notification.Channel.WHATSAPP,
            fallback_channel=Notification.Channel.TELEGRAM,
            recipient="123456789",
            message="Fallback test",
            tenant_id="tenant-sprint3",
        )

    notif.refresh_from_db()
    assert notif.status == DurableNotificationStatus.SENT
    assert notif.provider_response.get("via_fallback") is True
    mock_wa.assert_called_once()
    mock_tg.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_fallback_all_fail_dead_letter():
    """When both primary and fallback fail, notification is dead-lettered."""
    case = _make_case("case-fallback-dead")

    with patch("notifications.channels.whatsapp.deliver") as mock_wa, \
         patch("notifications.channels.telegram.deliver") as mock_tg:
        mock_wa.return_value = (False, {"error": "twilio_down"})
        mock_tg.return_value = (False, {"error": "telegram_down"})

        notif = DurableNotificationService.submit_sync(
            notification_id="nid-fallback-dead",
            case_id="case-fallback-dead",
            channel=Notification.Channel.WHATSAPP,
            fallback_channel=Notification.Channel.TELEGRAM,
            recipient="123456789",
            message="Both fail test",
            tenant_id="tenant-sprint3",
            max_retries=1,  # fail immediately after 1 attempt
        )

    notif.refresh_from_db()
    assert notif.status == DurableNotificationStatus.FAILED
    assert notif.is_dead is True

    # Audit trail should exist
    attempts = NotificationDeliveryAttempt.objects.filter(notification=notif)
    assert attempts.count() >= 1


# ══════════════════════════════════════════════════════════════════════════════
#  Circuit Breaker with Notification Channels
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_circuit_breaker_opens_after_failures():
    """Circuit opens after CIRCUIT_FAILURE_THRESHOLD failures on a channel."""
    channel = "whatsapp"
    NotificationProviderHealth.objects.filter(channel=channel).delete()

    for _ in range(5):
        _record_failure(channel)

    assert _circuit_is_open(channel) is True


@pytest.mark.django_db(transaction=True)
def test_circuit_breaker_blocks_delivery():
    """When circuit is open, dispatch returns failure immediately."""
    case = _make_case("case-circuit-block")
    channel = Notification.Channel.WHATSAPP
    NotificationProviderHealth.objects.filter(channel=channel).delete()

    # Open the circuit
    for _ in range(5):
        _record_failure(channel)

    with patch("notifications.channels.whatsapp.deliver") as mock_wa:
        notif = DurableNotificationService.submit_sync(
            notification_id="nid-circuit-block",
            case_id="case-circuit-block",
            channel=channel,
            recipient="+5511999999999",
            message="Should be blocked",
            tenant_id="tenant-sprint3",
            max_retries=1,
        )

    # Delivery backend should NOT have been called — circuit was open
    mock_wa.assert_not_called()

    notif.refresh_from_db()
    assert notif.status == DurableNotificationStatus.FAILED


@pytest.mark.django_db(transaction=True)
def test_circuit_breaker_recovers_after_reset():
    """Circuit resets after cooldown period."""
    import time

    channel = "telegram_recovery"
    NotificationProviderHealth.objects.filter(channel=channel).delete()

    for _ in range(5):
        _record_failure(channel)

    assert _circuit_is_open(channel) is True

    # Simulate cooldown by backdating opened_at
    health = NotificationProviderHealth.objects.get(channel=channel)
    health.opened_at = dj_timezone.now() - timedelta(seconds=health.reset_after_seconds + 1)
    health.save(update_fields=["opened_at"])

    assert _circuit_is_open(channel) is False


# ══════════════════════════════════════════════════════════════════════════════
#  Webhook Handlers
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_whatsapp_webhook_status_update():
    """WhatsApp status webhook updates notification record."""
    from notifications.views import whatsapp_status_callback

    case = _make_case("case-wa-webhook")

    notif = DurableNotificationService.submit_sync(
        notification_id="nid-wa-webhook",
        case_id="case-wa-webhook",
        channel=Notification.Channel.LOG,  # use LOG so it always succeeds
        recipient="log-test",
        message="Webhook test",
        tenant_id="tenant-sprint3",
    )
    # Manually set a SID in provider_response
    notif.provider_response = {"sid": "SM_webhook_test"}
    notif.save(update_fields=["provider_response"])

    factory = RequestFactory()
    request = factory.post(
        "/webhooks/whatsapp/status/",
        data={
            "MessageSid": "SM_webhook_test",
            "MessageStatus": "delivered",
            "To": "whatsapp:+5511999999999",
            "From": "whatsapp:+14155238886",
            "ErrorCode": "",
        },
    )

    response = whatsapp_status_callback(request)
    assert response.status_code == 200

    notif.refresh_from_db()
    assert notif.provider_response.get("delivery_status") == "delivered"


@pytest.mark.django_db(transaction=True)
def test_telegram_webhook_callback_query():
    """Telegram webhook handles approval callback query."""
    from notifications.views import telegram_webhook

    factory = RequestFactory()
    update = {
        "update_id": 1,
        "callback_query": {
            "id": "query-001",
            "from": {"id": 42, "first_name": "João", "last_name": "Silva"},
            "message": {
                "message_id": 100,
                "chat": {"id": 42},
            },
            "data": json.dumps({"action": "approve", "approval_id": "apv-tg-test"}),
        },
    }

    request = factory.post(
        "/webhooks/telegram/",
        data=json.dumps(update),
        content_type="application/json",
    )

    with patch("approvals.gateway.ApprovalGateway") as MockGateway, \
         patch("notifications.views._answer_callback") as mock_answer, \
         patch("notifications.views._edit_message_text") as mock_edit:
        MockGateway.decide_approval.return_value = True

        response = telegram_webhook(request)

    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["ok"] is True
    assert body["decision"] == "approved"
    MockGateway.decide_approval.assert_called_once_with(
        approval_id="apv-tg-test",
        decision="approved",
        decided_by="telegram:42",
        notes="Via Telegram by João Silva",
    )


@pytest.mark.django_db(transaction=True)
def test_telegram_webhook_rejects_invalid_json():
    """Telegram webhook returns 400 on malformed JSON."""
    from notifications.views import telegram_webhook

    factory = RequestFactory()
    request = factory.post(
        "/webhooks/telegram/",
        data="not-json",
        content_type="application/json",
    )

    response = telegram_webhook(request)
    assert response.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
#  End-to-End Pipeline: Submit → Deliver → Audit
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db(transaction=True)
def test_e2e_email_notification():
    """Full pipeline: submit email → deliver → audit trail."""
    case = _make_case("case-e2e-email")

    with patch("notifications.channels.email.EmailMultiAlternatives") as MockEmail:
        instance = MockEmail.return_value
        instance.send.return_value = 1

        notif = DurableNotificationService.submit_sync(
            notification_id="nid-e2e-email",
            case_id="case-e2e-email",
            channel=Notification.Channel.EMAIL,
            recipient="user@example.com",
            message="E2E email test",
            subject="Teste E2E",
            tenant_id="tenant-sprint3",
        )

    notif.refresh_from_db()
    assert notif.status == DurableNotificationStatus.SENT
    assert notif.attempts == 1
    assert notif.sent_at is not None

    # Verify audit trail
    attempts = NotificationDeliveryAttempt.objects.filter(notification=notif)
    assert attempts.count() == 1
    assert attempts.first().outcome == NotificationDeliveryAttempt.Outcome.SUCCESS


@pytest.mark.django_db(transaction=True)
def test_e2e_telegram_with_approval():
    """Full pipeline: submit Telegram with approval keyboard."""
    case = _make_case("case-e2e-tg")

    api_response = {"ok": True, "result": {"message_id": 77}}

    with patch("notifications.channels.telegram._api_call", return_value=api_response), \
         patch("notifications.channels.telegram.settings") as mock_settings:
        mock_settings.TELEGRAM_ENABLED = True
        mock_settings.TELEGRAM_BOT_TOKEN = "test-token"

        notif = DurableNotificationService.submit_sync(
            notification_id="nid-e2e-tg",
            case_id="case-e2e-tg",
            channel=Notification.Channel.TELEGRAM,
            recipient="42",
            message="Aprovar R$10.000?",
            tenant_id="tenant-sprint3",
            context={"approval_id": "apv-e2e"},
        )

    notif.refresh_from_db()
    assert notif.status == DurableNotificationStatus.SENT
    assert notif.provider_response.get("message_id") == 77
