"""Approval models used by the orchestration layer."""
from django.conf import settings
from django.db import models

from orchestrator.enums import ApprovalStatus


class Approval(models.Model):
    """Represents a required human approval."""

    approval_id = models.CharField(max_length=128, unique=True)
    case = models.ForeignKey("orchestrator.Case", on_delete=models.CASCADE, related_name="approvals")
    approval_type = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    requested_by_agent = models.CharField(max_length=100)
    tenant_id = models.CharField(max_length=100, default="default")
    correlation_id = models.CharField(max_length=100, blank=True, db_index=True)
    trace_id = models.CharField(max_length=100, blank=True)
    causation_id = models.CharField(max_length=128, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    deadline_at = models.DateTimeField(null=True, blank=True)
    escalation_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    approvers = models.JSONField(default=list, blank=True)
    escalated_to = models.JSONField(default=list, blank=True)
    escalation_reason = models.TextField(blank=True)
    approval_fields = models.JSONField(default=list, blank=True)
    policy_snapshot = models.JSONField(default=dict, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    summary = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    decision_comment = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "deadline_at"]),
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["correlation_id"]),
        ]

    def __str__(self) -> str:
        return f"Approval {self.approval_id} ({self.status})"
