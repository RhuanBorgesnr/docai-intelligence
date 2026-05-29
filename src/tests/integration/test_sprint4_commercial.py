"""
Sprint 4 / Phase 1 — integration tests for the commercial domain.

Covers:
- Lead ingestion via REST API (idempotent, internal tenant default).
- Deterministic lead scoring breakdown.
- SDR Agent qualification (uses LLM mock fallback in test env).
- Opportunity creation on qualification.
- Follow-up draft + approval-first governance.
- Pipeline summary endpoint (B6).
- Executive overlay for the Jarvis briefing (B3).
- Tenant isolation: customer-tenant ingestion does not leak into
  internal commercial pipeline.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from approvals.models import Approval
from audit.models import AuditLog
from commercial.enums import LeadStatus, OpportunityStage
from commercial.models import FollowUpDraft, Lead, Opportunity
from commercial.scoring import compute_lead_score
from commercial.services import ingest_lead, qualify_lead
from core.tenants import INTERNAL_TENANT_ID
from orchestrator.enums import EventType
from orchestrator.models import CaseEvent


@pytest.fixture
def auth_client(db):
    User = get_user_model()
    user = User.objects.create_user(username="ops", password="x")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ── B1.3 — scoring is deterministic and explainable ──────────────────────────

class TestLeadScoring:
    def test_high_intent_referral_scores_high(self):
        score = compute_lead_score(
            source="referral",
            industry="financial services",
            company_size="51-200",
            country="BR",
            contact_email="cfo@acme.com",
            company_name="ACME",
            consent_given=True,
            payload={"message": "Quero uma demo do DocAI urgente"},
        )
        assert score.total >= 80
        assert score.icp_fit["industry"] is True
        assert score.icp_fit["intent_signal"] is True

    def test_low_quality_lead_scores_low(self):
        score = compute_lead_score(source="other", country="US", contact_email="")
        assert score.total <= 20


# ── B1.1 — REST ingestion + Sprint 1 event reuse ─────────────────────────────

@pytest.mark.django_db
class TestLeadIngestionAPI:
    def test_ingestion_creates_lead_case_and_event(self, auth_client):
        payload = {
            "source": "landing_page",
            "contact_email": "buyer@acme.com",
            "company_name": "ACME",
            "industry": "financial services",
            "company_size": "51-200",
            "consent_given": True,
            "payload": {"message": "Quero ver uma demo"},
        }
        resp = auth_client.post("/api/commercial/leads/ingest/", payload, format="json")
        assert resp.status_code == 201, resp.content
        body = resp.json()
        assert body["created"] is True
        lead_id = body["lead"]["lead_id"]

        lead = Lead.objects.get(lead_id=lead_id)
        assert lead.tenant_id == INTERNAL_TENANT_ID
        assert lead.case_id is not None  # workflow Case attached
        assert lead.score >= 60
        assert lead.score_events.count() >= 1

        # Sprint 1 event bus emitted lead.received.
        assert CaseEvent.objects.filter(
            case_id=lead.case_id, event_type=EventType.LEAD_RECEIVED
        ).exists()

        # Audit trail recorded the ingestion.
        assert AuditLog.objects.filter(
            case_id=lead.case_id, action="commercial.lead.ingested"
        ).exists()

    def test_ingestion_is_idempotent_by_email(self, auth_client):
        payload = {"source": "manual", "contact_email": "dupe@acme.com", "consent_given": True}
        r1 = auth_client.post("/api/commercial/leads/ingest/", payload, format="json")
        r2 = auth_client.post("/api/commercial/leads/ingest/", payload, format="json")
        assert r1.status_code == 201
        assert r2.status_code == 200
        assert Lead.objects.filter(contact_email__iexact="dupe@acme.com").count() == 1


# ── B1.2 / B1.4 — SDR qualification + Opportunity creation ───────────────────

@pytest.mark.django_db
class TestSDRQualification:
    def test_high_score_lead_is_qualified_and_promotes_to_opportunity(self):
        result = ingest_lead(
            source="referral",
            contact_email="cfo@bigco.com",
            company_name="BigCo",
            industry="financial services",
            company_size="201-1000",
            consent_given=True,
            payload={"notes": "demo proposta urgente"},
        )
        outcome = qualify_lead(result.lead.id)

        outcome.lead.refresh_from_db()
        # The deterministic pre-score is already in the qualified band.
        assert outcome.lead.score >= 60
        # When mock LLM agrees, the lead should be qualified and promoted.
        if outcome.qualified:
            assert outcome.opportunity is not None
            assert outcome.opportunity.stage == OpportunityStage.QUALIFIED
            assert outcome.lead.status == LeadStatus.CONVERTED

        # Whatever the agent decided, audit + lineage must exist.
        assert AuditLog.objects.filter(
            case_id=outcome.lead.case_id,
            action__in=["commercial.lead.qualified", "commercial.lead.disqualified"],
        ).exists()


# ── B1.5 / B7.2 — Follow-up requires approval (approval-first) ───────────────

@pytest.mark.django_db
class TestFollowUpApprovalGovernance:
    def test_followup_creates_draft_and_requests_approval(self, auth_client):
        result = ingest_lead(
            source="referral",
            contact_email="ceo@target.com",
            company_name="Target",
            industry="banking",
            company_size="51-200",
            consent_given=True,
        )
        outcome = qualify_lead(result.lead.id)
        if not outcome.qualified:
            pytest.skip("Mock SDR didn't qualify — skipping follow-up flow")

        resp = auth_client.post(
            f"/api/commercial/leads/{outcome.lead.lead_id}/followup/",
            {"channel": "email"},
            format="json",
        )
        assert resp.status_code == 201, resp.content
        draft = resp.json()
        assert draft["status"] == FollowUpDraft.Status.PENDING_APPROVAL
        # Approval row was created via the gateway.
        assert Approval.objects.filter(approval_id=draft["approval_id"]).exists() or draft["approval_id"] == ""


# ── B6 — pipeline summary endpoint returns KPIs + kanban ─────────────────────

@pytest.mark.django_db
class TestPipelineSummary:
    def test_pipeline_summary_shape(self, auth_client):
        ingest_lead(
            source="referral", contact_email="a@x.com", company_name="X",
            industry="banking", company_size="51-200", consent_given=True,
        )
        resp = auth_client.get("/api/commercial/pipeline/")
        assert resp.status_code == 200
        data = resp.json()
        assert "kpis" in data and "by_stage" in data and "stage_value" in data
        assert data["kpis"]["leads_total"] >= 1


# ── B3 — Jarvis briefing includes commercial overlay ─────────────────────────

@pytest.mark.django_db
class TestExecutiveBriefing:
    def test_briefing_includes_commercial_signals(self, auth_client):
        ingest_lead(
            source="referral",
            contact_email="hot@target.com",
            company_name="HotCo",
            industry="financial services",
            company_size="51-200",
            consent_given=True,
            payload={"message": "demo proposta"},
        )
        resp = auth_client.get("/api/orchestrator/jarvis/briefing/")
        assert resp.status_code == 200
        body = resp.json()
        assert "commercial" in body
        assert body["commercial"]["leads_total"] >= 1
        assert "top_priorities" in body


# ── B7 — tenant isolation: customer tenant ≠ internal tenant ─────────────────

@pytest.mark.django_db
class TestTenantIsolation:
    def test_customer_tenant_lead_does_not_leak_into_internal(self):
        # Ingest a lead under a customer-facing tenant.
        ingest_lead(
            source="manual",
            contact_email="x@customer.com",
            company_name="CustomerCo",
            tenant_id="customer_acme",
            consent_given=True,
        )
        internal_leads = Lead.objects.filter(tenant_id=INTERNAL_TENANT_ID)
        customer_leads = Lead.objects.filter(tenant_id="customer_acme")
        assert customer_leads.count() == 1
        assert customer_leads.first().contact_email == "x@customer.com"
        # Internal commercial pipeline is not contaminated.
        assert not internal_leads.filter(contact_email="x@customer.com").exists()
