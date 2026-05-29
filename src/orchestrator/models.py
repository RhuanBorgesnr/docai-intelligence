"""Core models for workflow orchestration."""
from django.db import models

from .enums import CaseState, DurableEventStatus, EventType, Priority, WorkflowStatus


class Case(models.Model):
    """Represents a business/operational case handled by Jarvis."""

    external_ref = models.CharField(max_length=128, unique=True, null=True, blank=True)
    tenant_id = models.CharField(max_length=100, default="default")
    title = models.CharField(max_length=255, blank=True)
    state = models.CharField(max_length=50, choices=CaseState.choices, default=CaseState.NEW)
    workflow_status = models.CharField(
        max_length=30,
        choices=WorkflowStatus.choices,
        default=WorkflowStatus.RUNNING,
    )
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    correlation_id = models.CharField(max_length=100, db_index=True)
    trace_id = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant_id", "state"]),
            models.Index(fields=["correlation_id"]),
        ]

    def __str__(self) -> str:
        return f"Case {self.id} [{self.state}]"


class CaseEvent(models.Model):
    """Stores incoming and generated workflow events."""

    event_id = models.CharField(max_length=128, unique=True)
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=80, choices=EventType.choices)
    event_version = models.CharField(max_length=20, default="1.0")
    source = models.CharField(max_length=120)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    occurred_at = models.DateTimeField()
    correlation_id = models.CharField(max_length=100, db_index=True)
    trace_id = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["case", "created_at"]),
            models.Index(fields=["event_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} ({self.event_id})"


class CaseTask(models.Model):
    """Tracks internal tasks spawned by workflows."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=200)
    assignee_agent = models.CharField(max_length=100, blank=True)
    is_completed = models.BooleanField(default=False)
    due_at = models.DateTimeField(null=True, blank=True)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["case", "is_completed"])]

    def __str__(self) -> str:
        return f"Task {self.id} for case {self.case_id}"


class DLQEvent(models.Model):
    """Stores unrecoverable workflow events for replay."""

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="dlq_events")
    original_event = models.ForeignKey(
        CaseEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dlq_entries",
    )
    reason_code = models.CharField(max_length=120)
    error_message = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    replayable = models.BooleanField(default=True)
    payload = models.JSONField(default=dict)
    trace_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["case", "created_at"])]

    def __str__(self) -> str:
        return f"DLQ {self.id} for case {self.case_id}"


class EventOutbox(models.Model):
    """Durable event outbox for guaranteed publication and replay."""

    event_id = models.CharField(max_length=128, unique=True)
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name="outbox_events",
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=120)
    event_version = models.CharField(max_length=20, default="1.0")
    source = models.CharField(max_length=120)
    tenant_id = models.CharField(max_length=100, default="default")
    correlation_id = models.CharField(max_length=100, db_index=True)
    trace_id = models.CharField(max_length=100, blank=True)
    causation_id = models.CharField(max_length=128, blank=True)
    payload = models.JSONField(default=dict)
    meta = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=DurableEventStatus.choices, default=DurableEventStatus.PENDING)
    available_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "available_at"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["correlation_id"]),
        ]


class EventInbox(models.Model):
    """Deduplication and causal tracking for consumed durable events."""

    consumer = models.CharField(max_length=120)
    event_id = models.CharField(max_length=128)
    event_type = models.CharField(max_length=120)
    tenant_id = models.CharField(max_length=100, default="default")
    correlation_id = models.CharField(max_length=100, blank=True)
    trace_id = models.CharField(max_length=100, blank=True)
    payload_hash = models.CharField(max_length=64, blank=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["consumer", "event_id"], name="uniq_event_inbox_consumer_event"),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "processed_at"]),
            models.Index(fields=["event_type"]),
        ]
