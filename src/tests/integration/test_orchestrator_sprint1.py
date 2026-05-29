"""Integration tests for orchestrator Sprint 1 foundations."""
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from memory.models import MemorySnapshot
from orchestrator.enums import CaseState, EventType
from orchestrator.models import CaseEvent
from orchestrator.services import ingest_event
from orchestrator.workflow import apply_transition


@pytest.mark.django_db
class TestOrchestratorEventIngestion:
    def test_event_ingestion_is_idempotent(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(username="jarvis_admin", password="secret123")

        client = APIClient()
        client.force_authenticate(user=user)

        payload = {
            "event_id": "evt_sprint1_ingestion_1",
            "event_type": EventType.LEAD_RECEIVED,
            "source": "tests",
            "occurred_at": timezone.now().isoformat(),
            "correlation_id": "corr_sprint1",
            "payload": {
                "case_id": "ext_case_1",
                "title": "Lead inbound ACME",
            },
            "meta": {
                "trace_id": "trace_sprint1",
            },
        }

        response_1 = client.post("/api/orchestrator/events/", payload, format="json")
        response_2 = client.post("/api/orchestrator/events/", payload, format="json")

        assert response_1.status_code == 201
        assert response_2.status_code == 200
        assert CaseEvent.objects.filter(event_id="evt_sprint1_ingestion_1").count() == 1


@pytest.mark.django_db
class TestOrchestratorTransitions:
    def test_transition_new_to_triage_and_snapshot(self):
        ingestion_result = ingest_event(
            data={
                "event_id": "evt_sprint1_transition_1",
                "event_type": EventType.LEAD_RECEIVED,
                "source": "tests",
                "occurred_at": timezone.now(),
                "correlation_id": "corr_transition_1",
                "payload": {
                    "case_id": "ext_case_transition",
                    "title": "Lead transition test",
                },
                "meta": {
                    "trace_id": "trace_transition_1",
                },
            }
        )

        result = apply_transition(ingestion_result.event)

        ingestion_result.event.case.refresh_from_db()

        assert result.changed is True
        assert result.previous_state == CaseState.NEW
        assert ingestion_result.event.case.state == CaseState.TRIAGE
        assert MemorySnapshot.objects.filter(case=ingestion_result.event.case).exists()
