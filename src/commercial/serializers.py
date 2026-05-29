"""DRF serializers for the commercial API."""
from __future__ import annotations

from rest_framework import serializers

from commercial.enums import LeadSource
from commercial.models import FollowUpDraft, Lead, LeadScoreEvent, Opportunity


class LeadIngestionSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=LeadSource.choices, default=LeadSource.MANUAL)
    contact_name = serializers.CharField(required=False, allow_blank=True, default="")
    contact_email = serializers.EmailField(required=False, allow_blank=True, default="")
    contact_phone = serializers.CharField(required=False, allow_blank=True, default="")
    company_name = serializers.CharField(required=False, allow_blank=True, default="")
    industry = serializers.CharField(required=False, allow_blank=True, default="")
    company_size = serializers.CharField(required=False, allow_blank=True, default="")
    country = serializers.CharField(required=False, allow_blank=True, default="BR")
    payload = serializers.DictField(required=False, default=dict)
    consent_given = serializers.BooleanField(required=False, default=False)
    external_lead_id = serializers.CharField(required=False, allow_blank=True, default="")


class LeadScoreEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadScoreEvent
        fields = ("id", "score_before", "score_after", "reason", "details", "created_at")


class LeadSerializer(serializers.ModelSerializer):
    score_events = LeadScoreEventSerializer(many=True, read_only=True)
    case_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Lead
        fields = (
            "id", "lead_id", "tenant_id", "case_id",
            "source", "status", "score",
            "contact_name", "contact_email", "contact_phone",
            "company_name", "industry", "company_size", "country",
            "payload", "icp_fit", "qualification_reason",
            "consent_given", "correlation_id",
            "created_at", "updated_at", "last_event_at",
            "score_events",
        )
        read_only_fields = fields


class OpportunitySerializer(serializers.ModelSerializer):
    lead_id = serializers.CharField(source="lead.lead_id", read_only=True)
    company_name = serializers.CharField(source="lead.company_name", read_only=True)
    contact_email = serializers.CharField(source="lead.contact_email", read_only=True)
    score = serializers.IntegerField(source="lead.score", read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Opportunity
        fields = (
            "id", "opportunity_id", "tenant_id", "stage",
            "estimated_value", "win_probability", "owner_user_id",
            "lead_id", "company_name", "contact_email", "score",
            "notes", "metadata",
            "is_active", "created_at", "updated_at", "closed_at",
        )
        read_only_fields = fields


class OpportunityStageUpdateSerializer(serializers.Serializer):
    stage = serializers.CharField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class FollowUpDraftSerializer(serializers.ModelSerializer):
    lead_id = serializers.CharField(source="lead.lead_id", read_only=True)

    class Meta:
        model = FollowUpDraft
        fields = (
            "id", "draft_id", "tenant_id", "lead_id",
            "channel", "subject", "body", "status",
            "approval_id", "notification_id",
            "created_by_agent", "correlation_id", "lineage",
            "created_at", "updated_at", "sent_at",
        )
        read_only_fields = fields


class FollowUpRequestSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(
        choices=FollowUpDraft.Channel.choices,
        default=FollowUpDraft.Channel.EMAIL,
    )
    extra_context = serializers.DictField(required=False, default=dict)
