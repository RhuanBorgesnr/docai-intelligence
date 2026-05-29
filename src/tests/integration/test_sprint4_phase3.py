"""
Sprint 4 / Phase 3 — integration tests.

Covers:
- Agent Charter Registry (org chart with all 7 agents).
- Agent Metrics computation for each agent.
- Agent Routines execution (SDR stale check, Sales followup, etc.).
- Webhook handler (Typeform, HubSpot, generic).
- Demo Scheduler (schedule + audit trail).
- Agent Team API endpoints (/agents/team/, /agents/<type>/).
- Executive overlay includes team snapshot.
- Followup approval notification.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from agent_runtime.prompt_registry import AgentType
from commercial.models import Lead, Opportunity, FollowUpDraft
from commercial.enums import LeadStatus, OpportunityStage
from core.tenants import INTERNAL_TENANT_ID


User = get_user_model()


@pytest.fixture
def staff_client(db):
    user = User.objects.create_user(username="ops3", password="ops3pass", is_staff=True)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def normal_client(db):
    user = User.objects.create_user(username="client3", password="client3pass", is_staff=False)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def lead_qualified(db):
    """A qualified lead for testing."""
    from commercial.services import ingest_lead
    result = ingest_lead(
        source="manual",
        contact_email="phase3@docai.ai",
        contact_name="Phase 3 Lead",
        company_name="Empresa Phase 3",
        industry="tecnologia",
        payload={"company_size": "51-200"},
        consent_given=True,
    )
    lead = result.lead
    lead.status = LeadStatus.QUALIFIED
    lead.score = 75
    lead.save(update_fields=["status", "score"])
    return lead


# ── Agent Charter Registry ────────────────────────────────────────────────────

class TestAgentCharter:
    def test_all_seven_agents_registered(self):
        from agent_runtime.agent_charter import AGENT_TEAM
        assert len(AGENT_TEAM) == 7
        expected = {AgentType.JARVIS, AgentType.INTAKE, AgentType.SDR,
                    AgentType.SALES, AgentType.DOCAI_OPERATOR, AgentType.SUPPORT,
                    AgentType.ANALYST}
        assert set(AGENT_TEAM.keys()) == expected

    def test_charter_has_all_fields(self):
        from agent_runtime.agent_charter import AGENT_TEAM
        for agent_type, charter in AGENT_TEAM.items():
            assert charter.title, f"{agent_type} missing title"
            assert charter.emoji, f"{agent_type} missing emoji"
            assert charter.role_summary, f"{agent_type} missing role_summary"
            assert len(charter.responsibilities) > 0, f"{agent_type} missing responsibilities"
            assert len(charter.deliverables) > 0, f"{agent_type} missing deliverables"
            assert len(charter.kpis) > 0, f"{agent_type} missing kpis"
            assert len(charter.autonomy) > 0, f"{agent_type} missing autonomy"
            assert charter.business_impact, f"{agent_type} missing business_impact"
            assert isinstance(charter.communicates_with, tuple)

    def test_team_summary_serializable(self):
        from agent_runtime.agent_charter import get_team_summary
        summary = get_team_summary()
        assert len(summary) == 7
        for agent in summary:
            assert "agent_type" in agent
            assert "title" in agent
            assert "emoji" in agent
            assert "status" in agent
            assert "communicates_with" in agent

    def test_charter_detail_serializable(self):
        from agent_runtime.agent_charter import get_charter_detail
        detail = get_charter_detail(AgentType.SDR)
        assert detail["agent_type"] == "sdr"
        assert len(detail["responsibilities"]) > 0
        assert len(detail["routines"]) > 0
        assert len(detail["kpis"]) > 0
        assert "celery_task" in detail["routines"][0]


# ── Agent Metrics ─────────────────────────────────────────────────────────────

class TestAgentMetrics:
    @pytest.mark.django_db
    def test_compute_sdr_metrics(self, lead_qualified):
        from agent_runtime.agent_metrics import compute_sdr_metrics
        result = compute_sdr_metrics(INTERNAL_TENANT_ID)
        assert result["agent"] == "sdr"
        assert "leads_qualified_24h" in result["kpis"]
        assert "hot_lead_response_time" in result["kpis"]

    @pytest.mark.django_db
    def test_compute_sales_metrics(self, lead_qualified):
        from agent_runtime.agent_metrics import compute_sales_metrics
        result = compute_sales_metrics(INTERNAL_TENANT_ID)
        assert result["agent"] == "sales"
        assert "pipeline_value" in result["kpis"]

    @pytest.mark.django_db
    def test_compute_team_metrics(self, lead_qualified):
        from agent_runtime.agent_metrics import compute_team_metrics
        results = compute_team_metrics(INTERNAL_TENANT_ID)
        assert len(results) == 7
        agent_names = {r["agent"] for r in results}
        assert "sdr" in agent_names
        assert "sales" in agent_names
        assert "jarvis" in agent_names

    @pytest.mark.django_db
    def test_compute_single_agent_metric(self):
        from agent_runtime.agent_metrics import compute_agent_metrics
        result = compute_agent_metrics(AgentType.JARVIS)
        assert result["agent"] == "jarvis"
        assert "agent_uptime" in result["kpis"]


# ── Agent Routines ────────────────────────────────────────────────────────────

class TestAgentRoutines:
    @pytest.mark.django_db
    def test_sdr_stale_lead_check(self, lead_qualified):
        from agent_runtime.routines import sdr_stale_lead_check
        result = sdr_stale_lead_check(INTERNAL_TENANT_ID)
        assert "stale_leads" in result
        assert "checked_at" in result

    @pytest.mark.django_db
    def test_sales_followup_check(self, lead_qualified):
        from agent_runtime.routines import sales_followup_check
        result = sales_followup_check(INTERNAL_TENANT_ID)
        assert "leads_needing_followup" in result

    @pytest.mark.django_db
    def test_sales_pipeline_stale_check(self, lead_qualified):
        from agent_runtime.routines import sales_pipeline_stale_check
        result = sales_pipeline_stale_check(INTERNAL_TENANT_ID)
        assert "stale_opportunities" in result

    @pytest.mark.django_db
    def test_docai_pending_demo_check(self, lead_qualified):
        from agent_runtime.routines import docai_pending_demo_check
        result = docai_pending_demo_check(INTERNAL_TENANT_ID)
        assert "pending_demos" in result

    @pytest.mark.django_db
    def test_theo_agent_health_check(self):
        from agent_runtime.routines import theo_agent_health_check
        result = theo_agent_health_check()
        assert "agents" in result
        assert len(result["agents"]) == 7

    @pytest.mark.django_db
    def test_intake_webhook_health(self, lead_qualified):
        from agent_runtime.routines import intake_webhook_health
        result = intake_webhook_health(INTERNAL_TENANT_ID)
        assert "leads_last_4h" in result
        assert "anomaly_detected" in result

    @pytest.mark.django_db
    def test_analyst_weekly_funnel(self, lead_qualified):
        from agent_runtime.routines import analyst_weekly_funnel
        result = analyst_weekly_funnel(INTERNAL_TENANT_ID)
        assert "funnel" in result
        funnel = result["funnel"]
        assert "leads_total" in funnel
        assert "conversion_lead_to_qualified" in funnel

    def test_celery_beat_schedule(self):
        from agent_runtime.routines import get_celery_beat_schedule
        schedule = get_celery_beat_schedule()
        assert len(schedule) >= 10
        assert "theo-daily-briefing" in schedule
        assert "sdr-stale-lead-check" in schedule
        assert "sales-followup-check" in schedule


# ── Webhook Handler ───────────────────────────────────────────────────────────

class TestWebhookHandler:
    @pytest.mark.django_db
    def test_generic_webhook(self):
        from commercial.webhooks import handle_webhook
        result = handle_webhook(
            source="landing_page",
            payload={
                "name": "Webhook Test",
                "email": "webhook@test.com",
                "company": "Webhook Corp",
                "industry": "SaaS",
            },
        )
        assert result["created"] is True
        assert result["source"] == "landing_page"
        assert "lead_id" in result

    @pytest.mark.django_db
    def test_typeform_webhook(self):
        from commercial.webhooks import handle_webhook
        payload = {
            "form_response": {
                "answers": [
                    {"field": {"ref": "name"}, "text": "Typeform Lead"},
                    {"field": {"ref": "email"}, "email": "typeform@test.com"},
                    {"field": {"ref": "company"}, "text": "Typeform Inc"},
                ],
            }
        }
        result = handle_webhook(source="typeform", payload=payload)
        assert result["created"] is True
        assert result["source"] == "typeform"

    @pytest.mark.django_db
    def test_webhook_idempotent(self):
        from commercial.webhooks import handle_webhook
        payload = {"email": "idem@test.com", "name": "Same Lead"}
        r1 = handle_webhook(source="generic", payload=payload)
        r2 = handle_webhook(source="generic", payload=payload)
        assert r1["created"] is True
        assert r2["created"] is False
        assert r1["lead_id"] == r2["lead_id"]

    def test_webhook_missing_contact(self):
        from commercial.webhooks import handle_webhook
        result = handle_webhook(source="generic", payload={"random": "data"})
        assert "error" in result

    def test_hmac_verification_pass(self):
        import hashlib, hmac as hmac_mod
        from commercial.webhooks import verify_hmac
        secret = "test_secret"
        body = b'{"test": true}'
        sig = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert verify_hmac(body, sig, secret) is True

    def test_hmac_verification_fail(self):
        from commercial.webhooks import verify_hmac
        assert verify_hmac(b"body", "wrong_sig", "secret") is False


# ── Demo Scheduler ────────────────────────────────────────────────────────────

class TestDemoScheduler:
    @pytest.mark.django_db
    def test_schedule_demo_creates_opportunity(self, lead_qualified):
        from commercial.demo_scheduler import schedule_demo
        result = schedule_demo(
            lead_id=lead_qualified.lead_id,
            notes="Phase 3 demo test",
            scheduled_by="test_ops",
        )
        assert result["lead_id"] == lead_qualified.lead_id
        assert "opportunity_id" in result
        assert result["stage"] == OpportunityStage.DEMO_SCHEDULED
        assert result["scheduled_by"] == "test_ops"

        # Verify opportunity was created
        opp = Opportunity.objects.get(opportunity_id=result["opportunity_id"])
        assert opp.stage == OpportunityStage.DEMO_SCHEDULED
        assert "demo_scheduled_at" in opp.metadata

    @pytest.mark.django_db
    def test_schedule_demo_audit_trail(self, lead_qualified):
        from commercial.demo_scheduler import schedule_demo
        from audit.models import AuditLog
        result = schedule_demo(lead_id=lead_qualified.lead_id)
        audit = AuditLog.objects.filter(
            action="demo.scheduled",
            details__entity_id=lead_qualified.lead_id,
        ).first()
        assert audit is not None
        assert audit.details["opportunity_id"] == result["opportunity_id"]


# ── API Endpoints ─────────────────────────────────────────────────────────────

class TestAgentTeamAPI:
    @pytest.mark.django_db
    def test_agent_team_list(self, staff_client):
        resp = staff_client.get("/api/commercial/agents/team/")
        assert resp.status_code == 200
        assert len(resp.data["team"]) == 7

    @pytest.mark.django_db
    def test_agent_detail(self, staff_client):
        resp = staff_client.get("/api/commercial/agents/sdr/")
        assert resp.status_code == 200
        assert resp.data["charter"]["agent_type"] == "sdr"
        assert "kpis" in resp.data["metrics"]

    @pytest.mark.django_db
    def test_agent_detail_unknown(self, staff_client):
        resp = staff_client.get("/api/commercial/agents/unknown_agent/")
        assert resp.status_code == 404

    @pytest.mark.django_db
    def test_run_routine_requires_staff(self, normal_client):
        resp = normal_client.post("/api/commercial/agents/sdr/routine/stale_lead_alert/")
        assert resp.status_code == 403

    @pytest.mark.django_db
    def test_schedule_demo_endpoint(self, staff_client, lead_qualified):
        resp = staff_client.post(
            f"/api/commercial/leads/{lead_qualified.lead_id}/schedule-demo/",
            {"notes": "API test demo"},
        )
        assert resp.status_code == 201
        assert "opportunity_id" in resp.data


# ── Executive Overlay with Team ───────────────────────────────────────────────

class TestExecutiveOverlayTeam:
    @pytest.mark.django_db
    def test_overlay_includes_team(self, lead_qualified):
        from orchestrator.executive_signals import build_executive_overlay
        overlay = build_executive_overlay(INTERNAL_TENANT_ID)
        assert "team" in overlay
        assert overlay["team"]["total_agents"] == 7
        assert overlay["team"]["active_agents"] >= 5
        assert len(overlay["team"]["agents"]) == 7


# ── Followup Approval Notification ───────────────────────────────────────────

class TestFollowupNotification:
    @pytest.mark.django_db
    def test_notify_followup_approved(self, lead_qualified):
        draft = FollowUpDraft.objects.create(
            lead=lead_qualified,
            channel="email",
            subject="Test follow-up",
            body="Test body",
            status=FollowUpDraft.Status.APPROVED,
        )
        from commercial.demo_scheduler import notify_followup_approved
        result = notify_followup_approved(draft.draft_id)
        assert result is True

    @pytest.mark.django_db
    def test_notify_nonexistent_draft(self):
        from commercial.demo_scheduler import notify_followup_approved
        result = notify_followup_approved("nonexistent_draft_123")
        assert result is False
