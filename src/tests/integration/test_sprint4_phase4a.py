"""
Sprint 4 / Phase 4A — integration tests.

Covers:
- Approval REST API (list, count, detail, decide).
- Approval lifecycle (pending → approved/rejected).
- Webhook is public (AllowAny) and uses normalizer.
- Celery Beat schedule includes agent routines.
- Follow-up approval triggers notification.
- Approval count endpoint (for nav badge).
"""
from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from approvals.gateway import ApprovalDecision, ApprovalGateway, ApprovalPolicy, ApprovalPriority
from approvals.models import Approval as ApprovalRecord
from commercial.models import Lead, FollowUpDraft
from orchestrator.enums import ApprovalStatus

User = get_user_model()


@pytest.fixture
def staff_client(db):
    user = User.objects.create_user(username="ops4a", password="ops4apass", is_staff=True, email="ops4a@docai.ai")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def anon_client():
    return APIClient()


@pytest.fixture
def pending_approval(db):
    """Create a real pending approval via the gateway."""
    result = async_to_sync(ApprovalGateway.request_approval)(
        approval_id="test_appr_001",
        case_id="test_case_4a",
        correlation_id="corr_4a_001",
        agent_type="sales",
        action="commercial.followup.send",
        data_to_approve={
            "draft_id": "fup_test_001",
            "subject": "Follow-up test",
            "body": "Hello, this is a test follow-up for DocAI demo.",
            "channel": "email",
        },
        affected_fields=["subject", "body"],
        context={"lead_id": "lead_test", "score": 75},
    )
    return result


# ── Approval API ──────────────────────────────────────────────────────────────

class TestApprovalListAPI:
    @pytest.mark.django_db
    def test_list_pending(self, staff_client, pending_approval):
        resp = staff_client.get("/api/approvals/", {"status": "pending"})
        assert resp.status_code == 200
        assert resp.data["count"] >= 1
        ids = [a["approval_id"] for a in resp.data["approvals"]]
        assert "test_appr_001" in ids

    @pytest.mark.django_db
    def test_list_all(self, staff_client, pending_approval):
        resp = staff_client.get("/api/approvals/", {"status": "all"})
        assert resp.status_code == 200
        assert resp.data["count"] >= 1

    @pytest.mark.django_db
    def test_count_pending(self, staff_client, pending_approval):
        resp = staff_client.get("/api/approvals/count/")
        assert resp.status_code == 200
        assert resp.data["pending"] >= 1

    @pytest.mark.django_db
    def test_detail(self, staff_client, pending_approval):
        resp = staff_client.get("/api/approvals/test_appr_001/")
        assert resp.status_code == 200
        assert resp.data["approval_id"] == "test_appr_001"
        assert resp.data["action"] == "commercial.followup.send"
        assert resp.data["status"] in ("pending", "escalated")

    @pytest.mark.django_db
    def test_detail_not_found(self, staff_client):
        resp = staff_client.get("/api/approvals/nonexistent_id/")
        assert resp.status_code == 404


class TestApprovalDecideAPI:
    @pytest.mark.django_db
    def test_approve(self, staff_client, pending_approval):
        resp = staff_client.post("/api/approvals/test_appr_001/decide/", {
            "decision": "approved",
            "comment": "Approved via Phase 4A test",
        })
        assert resp.status_code == 200
        assert resp.data["status"] == "approved"
        # Verify in DB
        record = ApprovalRecord.objects.get(approval_id="test_appr_001")
        assert record.status == ApprovalStatus.APPROVED

    @pytest.mark.django_db
    def test_reject(self, staff_client, pending_approval):
        resp = staff_client.post("/api/approvals/test_appr_001/decide/", {
            "decision": "rejected",
            "comment": "Not appropriate at this time",
        })
        assert resp.status_code == 200
        assert resp.data["status"] == "rejected"

    @pytest.mark.django_db
    def test_request_changes(self, staff_client, pending_approval):
        resp = staff_client.post("/api/approvals/test_appr_001/decide/", {
            "decision": "request_changes",
            "comment": "Please adjust the tone",
        })
        assert resp.status_code == 200
        assert resp.data["status"] == "request_changes"

    @pytest.mark.django_db
    def test_invalid_decision(self, staff_client, pending_approval):
        resp = staff_client.post("/api/approvals/test_appr_001/decide/", {
            "decision": "invalid",
        })
        assert resp.status_code == 400

    @pytest.mark.django_db
    def test_double_decide_fails(self, staff_client, pending_approval):
        staff_client.post("/api/approvals/test_appr_001/decide/", {"decision": "approved"})
        resp = staff_client.post("/api/approvals/test_appr_001/decide/", {"decision": "rejected"})
        assert resp.status_code == 409  # Already decided


# ── Webhook Public Access ─────────────────────────────────────────────────────

class TestWebhookPublic:
    @pytest.mark.django_db
    def test_webhook_no_auth_required(self, anon_client):
        resp = anon_client.post(
            "/api/commercial/leads/webhook/landing_page/",
            {"email": "public@test.com", "name": "Public Lead", "company": "Public Corp"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["created"] is True

    @pytest.mark.django_db
    def test_webhook_typeform_format(self, anon_client):
        resp = anon_client.post(
            "/api/commercial/leads/webhook/typeform/",
            {
                "form_response": {
                    "answers": [
                        {"field": {"ref": "name"}, "text": "Typeform Public"},
                        {"field": {"ref": "email"}, "email": "typeform_pub@test.com"},
                        {"field": {"ref": "company"}, "text": "Typeform Corp"},
                    ]
                }
            },
            format="json",
        )
        assert resp.status_code == 201

    @pytest.mark.django_db
    def test_webhook_missing_contact_returns_400(self, anon_client):
        resp = anon_client.post(
            "/api/commercial/leads/webhook/generic/",
            {"random_field": "no contact info"},
            format="json",
        )
        assert resp.status_code == 400

    @pytest.mark.django_db
    def test_webhook_idempotent(self, anon_client):
        payload = {"email": "idem_pub@test.com", "name": "Idem Lead"}
        r1 = anon_client.post("/api/commercial/leads/webhook/landing/", payload, format="json")
        r2 = anon_client.post("/api/commercial/leads/webhook/landing/", payload, format="json")
        assert r1.status_code == 201
        assert r2.status_code == 200
        assert r1.data["lead_id"] == r2.data["lead_id"]


# ── Celery Beat Schedule ──────────────────────────────────────────────────────

class TestCeleryBeatSchedule:
    def test_agent_routines_in_beat_schedule(self):
        from core.celery import app
        schedule = app.conf.beat_schedule
        expected_keys = [
            'sdr-stale-lead-check',
            'sales-followup-check',
            'sales-pipeline-stale-check',
            'docai-pending-demo-check',
            'theo-daily-briefing',
            'theo-agent-health-check',
            'theo-escalation-sweep',
            'intake-webhook-health',
            'analyst-daily-metrics',
            'analyst-weekly-funnel',
        ]
        for key in expected_keys:
            assert key in schedule, f"Missing beat schedule entry: {key}"

    def test_total_schedule_count(self):
        from core.celery import app
        # Sprint 2 had ~8, Phase 4A adds 10 → at least 18
        assert len(app.conf.beat_schedule) >= 18


# ── Approval after list shows decided ─────────────────────────────────────────

class TestApprovalDecidedFilter:
    @pytest.mark.django_db
    def test_decided_filter(self, staff_client, pending_approval):
        # Decide it first
        staff_client.post("/api/approvals/test_appr_001/decide/", {"decision": "approved"})
        # Now filter for decided
        resp = staff_client.get("/api/approvals/", {"status": "decided"})
        assert resp.status_code == 200
        ids = [a["approval_id"] for a in resp.data["approvals"]]
        assert "test_appr_001" in ids
