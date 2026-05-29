"""Serializers for orchestrator APIs."""
from rest_framework import serializers

from audit.models import AuditLog
from orchestrator.enums import EventType
from orchestrator.models import Case, CaseEvent


class EventIngestionSerializer(serializers.Serializer):
    event_id = serializers.CharField(max_length=128)
    event_type = serializers.ChoiceField(choices=EventType.choices)
    event_version = serializers.CharField(max_length=20, default="1.0")
    occurred_at = serializers.DateTimeField(required=False)
    source = serializers.CharField(max_length=120)
    tenant_id = serializers.CharField(max_length=100, required=False, default="default")
    correlation_id = serializers.CharField(max_length=100, required=False)
    priority = serializers.CharField(max_length=20, required=False)
    payload = serializers.JSONField(required=False)
    meta = serializers.JSONField(required=False)


class CaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Case
        fields = [
            "id",
            "external_ref",
            "tenant_id",
            "title",
            "state",
            "workflow_status",
            "priority",
            "correlation_id",
            "trace_id",
            "created_at",
            "updated_at",
        ]


class CaseEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseEvent
        fields = [
            "id",
            "event_id",
            "event_type",
            "event_version",
            "source",
            "priority",
            "occurred_at",
            "correlation_id",
            "trace_id",
            "payload",
            "meta",
            "created_at",
        ]


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id",
            "action",
            "actor_type",
            "actor_id",
            "trace_id",
            "correlation_id",
            "details",
            "created_at",
        ]
