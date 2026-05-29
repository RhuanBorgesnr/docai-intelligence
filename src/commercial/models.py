"""
Commercial domain models (Sprint 4 / B1).

Reuses the orchestrator ``Case`` as the durable workflow handle: every Lead
and Opportunity is linked to a Case, so the existing event bus, audit trail,
memory snapshots and approval gateway work without changes.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone

from commercial.enums import (
    ACTIVE_OPPORTUNITY_STAGES,
    LeadSource,
    LeadStatus,
    OpportunityStage,
)
from core.tenants import INTERNAL_TENANT_ID
from orchestrator.models import Case


def _new_lead_id() -> str:
    return f"lead_{uuid.uuid4().hex[:16]}"


def _new_opportunity_id() -> str:
    return f"opp_{uuid.uuid4().hex[:16]}"


def _new_followup_id() -> str:
    return f"fup_{uuid.uuid4().hex[:16]}"


class Lead(models.Model):
    """A commercial lead captured by the company that operates DocAI."""

    lead_id = models.CharField(max_length=64, unique=True, default=_new_lead_id)
    tenant_id = models.CharField(max_length=100, default=INTERNAL_TENANT_ID, db_index=True)

    case = models.ForeignKey(
        Case,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commercial_leads",
        help_text="Workflow case backing this lead.",
    )

    source = models.CharField(max_length=40, choices=LeadSource.choices, default=LeadSource.MANUAL)
    status = models.CharField(max_length=30, choices=LeadStatus.choices, default=LeadStatus.NEW, db_index=True)
    score = models.IntegerField(default=0, db_index=True, help_text="Lead score 0–100.")

    # Contact / company
    contact_name = models.CharField(max_length=200, blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")
    contact_phone = models.CharField(max_length=40, blank=True, default="")
    company_name = models.CharField(max_length=200, blank=True, default="")
    industry = models.CharField(max_length=100, blank=True, default="")
    company_size = models.CharField(max_length=50, blank=True, default="")
    country = models.CharField(max_length=80, blank=True, default="BR")

    payload = models.JSONField(default=dict, blank=True, help_text="Raw payload received from the channel.")
    icp_fit = models.JSONField(default=dict, blank=True, help_text="Per-criterion ICP fit assessment.")
    qualification_reason = models.TextField(blank=True, default="")

    correlation_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    consent_given = models.BooleanField(default=False, help_text="LGPD consent recorded at intake.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_event_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "score"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        label = self.contact_email or self.contact_name or self.company_name or "(unnamed)"
        return f"Lead {self.lead_id} — {label} [{self.status}]"


class LeadScoreEvent(models.Model):
    """Append-only history of lead score changes (audit-friendly)."""

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="score_events")
    score_before = models.IntegerField()
    score_after = models.IntegerField()
    reason = models.CharField(max_length=200, blank=True, default="")
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class Opportunity(models.Model):
    """A qualified opportunity moving through the commercial pipeline."""

    opportunity_id = models.CharField(max_length=64, unique=True, default=_new_opportunity_id)
    tenant_id = models.CharField(max_length=100, default=INTERNAL_TENANT_ID, db_index=True)

    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="opportunities")
    case = models.ForeignKey(
        Case,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commercial_opportunities",
    )

    stage = models.CharField(
        max_length=30,
        choices=OpportunityStage.choices,
        default=OpportunityStage.NEW,
        db_index=True,
    )
    estimated_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    win_probability = models.FloatField(default=0.0)
    owner_user_id = models.CharField(max_length=120, blank=True, default="")

    notes = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["tenant_id", "stage"]),
        ]

    @property
    def is_active(self) -> bool:
        return self.stage in ACTIVE_OPPORTUNITY_STAGES

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"Opportunity {self.opportunity_id} — {self.lead.company_name} [{self.stage}]"


class FollowUpDraft(models.Model):
    """A draft outbound message generated by Sales Agent — pending approval."""

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Status(models.TextChoices):
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    draft_id = models.CharField(max_length=64, unique=True, default=_new_followup_id)
    tenant_id = models.CharField(max_length=100, default=INTERNAL_TENANT_ID, db_index=True)

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="followups")
    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="followups",
    )

    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.EMAIL)
    subject = models.CharField(max_length=255, blank=True, default="")
    body = models.TextField()
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.PENDING_APPROVAL, db_index=True
    )

    approval_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    notification_id = models.CharField(max_length=128, blank=True, default="")
    created_by_agent = models.CharField(max_length=80, default="sales")
    correlation_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    lineage = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
