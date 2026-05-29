from django.urls import path

from notifications.views import telegram_webhook, whatsapp_status_callback

urlpatterns = [
    path("webhooks/whatsapp/status/", whatsapp_status_callback, name="whatsapp-status-callback"),
    path("webhooks/telegram/", telegram_webhook, name="telegram-webhook"),
]
