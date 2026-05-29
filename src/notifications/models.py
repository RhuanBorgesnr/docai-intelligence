"""Notification models for outbound channels."""
from django.db import models

from orchestrator.enums import DurableNotificationStatus


class Notification(models.Model):
    """Represents an outbound notification request/status."""

    class Channel(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        TELEGRAM = "telegram", "Telegram"
        EMAIL = "email", "Email"
        WEBHOOK = "webhook", "Webhook"
        PANEL = "panel", "Panel"
        LOG = "log", "Log"

    class Priority(models.TextChoices):
        CRITICAL = "critical", "Critical"
        HIGH = "high", "High"
        NORMAL = "normal", "Normal"
        LOW = "low", "Low"

    notification_id = models.CharField(max_length=128, unique=True)
    case = models.ForeignKey("orchestrator.Case", on_delete=models.CASCADE, related_name="notifications")
    tenant_id = models.CharField(max_length=100, default="default", db_index=True)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    fallback_channel = models.CharField(max_length=20, choices=Channel.choices, blank=True)
    recipient = models.CharField(max_length=255)
    subject = models.CharField(max_length=255, blank=True)
    message = models.TextField()
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(
        max_length=20,
        choices=DurableNotificationStatus.choices,
        default=DurableNotificationStatus.PENDING,
        db_index=True,
    )
    correlation_id = models.CharField(max_length=100, blank=True, db_index=True)
    trace_id = models.CharField(max_length=100, blank=True)
    causation_id = models.CharField(max_length=128, blank=True)
    idempotency_key = models.CharField(max_length=128, blank=True, db_index=True)
    template_name = models.CharField(max_length=120, blank=True)
    context = models.JSONField(default=dict, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    leased_until = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    provider_response = models.JSONField(default=dict, blank=True)
    is_dead = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["case", "status"]),
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["is_dead", "status"]),
        ]

    def __str__(self) -> str:
        return f"Notification {self.notification_id} ({self.channel})"


class NotificationDeliveryAttempt(models.Model):
    """Audit trail for every delivery attempt of a notification."""

    class Outcome(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"
        FALLBACK_SUCCESS = "fallback_success", "Fallback Success"

    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="delivery_attempts"
    )
    attempt_number = models.PositiveIntegerField()
    channel = models.CharField(max_length=20)
    recipient = models.CharField(max_length=255)
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    error = models.TextField(blank=True)
    provider_response = models.JSONField(default=dict, blank=True)
    duration_ms = models.FloatField(default=0.0)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["notification", "attempt_number"]),
        ]


class NotificationProviderHealth(models.Model):
    """Circuit-breaker state per channel/provider."""

    channel = models.CharField(max_length=20, unique=True)
    is_open = models.BooleanField(default=False)  # True = circuit open = failing
    failure_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    reset_after_seconds = models.PositiveIntegerField(default=60)
    failure_threshold = models.PositiveIntegerField(default=5)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["channel", "is_open"]),
        ]

    def __str__(self) -> str:
        state = "OPEN" if self.is_open else "closed"
        return f"ProviderHealth {self.channel} [{state}]"
