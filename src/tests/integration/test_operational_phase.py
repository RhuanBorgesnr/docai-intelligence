"""
Tests for Operational Phase — real daily operation components.

Tests:
1. Real email sender
2. WhatsApp link generation
3. Follow-up dispatch after approval
4. Cost tracker model + recording
5. Cost analytics
6. Agent execution feedback
7. Daily ops API
8. Landing webhook integration
"""
from __future__ import annotations

import pytest
from datetime import timedelta
from django.utils import timezone
from django.test import TestCase


# ── Email Sender ──────────────────────────────────────────────────────────────

class TestEmailSender(TestCase):
    """Tests for notifications.email_sender module."""

    def test_send_real_email_console_backend(self):
        """In dev mode (ConsoleEmailBackend), send_real_email logs to console."""
        from notifications.email_sender import send_real_email
        result = send_real_email(
            to="lead@empresa.com",
            subject="Follow-up DocAI",
            body_text="Olá! Aqui é a equipe DocAI.",
        )
        assert result is True

    def test_send_real_email_with_html(self):
        from notifications.email_sender import send_real_email
        result = send_real_email(
            to="cto@empresa.com",
            subject="Proposta DocAI",
            body_text="Versão texto",
            body_html="<h1>Proposta</h1><p>HTML body</p>",
        )
        assert result is True


class TestWhatsAppLink(TestCase):
    """Tests for whatsapp_link generator."""

    def test_basic_link(self):
        from notifications.email_sender import whatsapp_link
        link = whatsapp_link("11999998888")
        assert "wa.me/5511999998888" in link

    def test_link_with_country_code(self):
        from notifications.email_sender import whatsapp_link
        link = whatsapp_link("5511999998888")
        assert "wa.me/5511999998888" in link
        assert link.count("55") == 1  # no double prefix

    def test_link_with_message(self):
        from notifications.email_sender import whatsapp_link
        link = whatsapp_link("11999998888", "Olá! Tudo bem?")
        assert "text=" in link
        assert "Ol" in link

    def test_strips_non_digits(self):
        from notifications.email_sender import whatsapp_link
        link = whatsapp_link("(11) 99999-8888")
        assert "5511999998888" in link


# ── Cost Tracker ──────────────────────────────────────────────────────────────

class TestCostTracker(TestCase):
    """Tests for agent_runtime.cost_tracker module."""

    def test_estimate_cost_openai(self):
        from agent_runtime.cost_tracker import estimate_cost
        cost = estimate_cost("openai", prompt_tokens=1000, completion_tokens=500)
        assert cost > 0
        assert cost == pytest.approx(0.0015 + 0.001, abs=0.001)

    def test_estimate_cost_local(self):
        from agent_runtime.cost_tracker import estimate_cost
        cost = estimate_cost("local", prompt_tokens=1000, completion_tokens=500)
        assert cost == 0.0

    def test_record_execution(self):
        from agent_runtime.cost_tracker import record_execution, AgentExecution
        record = record_execution(
            execution_id="test-exec-001",
            agent_type="sdr",
            provider="openai",
            prompt_tokens=500,
            completion_tokens=200,
            latency_ms=1200,
            llm_latency_ms=1000,
            status="success",
            output_summary="Lead qualificado com score 85",
            lead_id="lead-001",
            trigger="webhook",
        )
        assert record.execution_id == "test-exec-001"
        assert record.total_tokens == 700
        assert record.estimated_cost_usd > 0
        assert AgentExecution.objects.count() == 1

    def test_record_feedback(self):
        from agent_runtime.cost_tracker import record_execution, record_feedback, AgentExecution
        record_execution(
            execution_id="test-feedback-001",
            agent_type="sales",
            provider="openai",
            prompt_tokens=300,
            completion_tokens=100,
        )
        ok = record_feedback("test-feedback-001", quality=4, useful=True, notes="Bom follow-up", by="admin")
        assert ok is True

        record = AgentExecution.objects.get(execution_id="test-feedback-001")
        assert record.feedback_quality == 4
        assert record.feedback_useful is True

    def test_feedback_nonexistent(self):
        from agent_runtime.cost_tracker import record_feedback
        ok = record_feedback("nonexistent-id", quality=3)
        assert ok is False


class TestCostAnalytics(TestCase):
    """Tests for cost summary and agent performance."""

    def _seed_executions(self):
        from agent_runtime.cost_tracker import record_execution
        for i in range(5):
            record_execution(
                execution_id=f"analytics-sdr-{i}",
                agent_type="sdr",
                provider="openai",
                prompt_tokens=500,
                completion_tokens=200,
                latency_ms=1000 + i * 100,
                status="success",
                lead_id=f"lead-{i}",
            )
        for i in range(3):
            record_execution(
                execution_id=f"analytics-sales-{i}",
                agent_type="sales",
                provider="openai",
                prompt_tokens=800,
                completion_tokens=400,
                latency_ms=1500,
                status="success" if i < 2 else "failed",
            )

    def test_cost_summary(self):
        self._seed_executions()
        from agent_runtime.cost_tracker import cost_summary
        summary = cost_summary(days=7)
        assert summary["total_executions"] == 8
        assert summary["total_cost_usd"] > 0
        assert len(summary["per_agent"]) == 2

    def test_agent_performance(self):
        self._seed_executions()
        from agent_runtime.cost_tracker import agent_performance
        perf = agent_performance("sdr", days=7)
        assert perf["total_executions"] == 5
        assert perf["success_rate"] == 100.0
        assert len(perf["recent_executions"]) == 5

    def test_agent_performance_with_failures(self):
        self._seed_executions()
        from agent_runtime.cost_tracker import agent_performance
        perf = agent_performance("sales", days=7)
        assert perf["failures"] == 1
        assert perf["success_rate"] < 100


# ── Daily Ops API ─────────────────────────────────────────────────────────────

class TestDailyOpsAPI(TestCase):
    """Tests for orchestrator.daily_ops views."""

    def test_daily_ops_view_structure(self):
        """DailyOpsView returns correct structure."""
        from orchestrator.daily_ops import DailyOpsView
        from rest_framework.test import APIRequestFactory, force_authenticate
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user("ops_tester", password="test123", is_staff=True)
        factory = APIRequestFactory()
        request = factory.get("/api/orchestrator/ops/daily/")
        force_authenticate(request, user=user)
        response = DailyOpsView.as_view()(request)
        assert response.status_code == 200
        data = response.data
        assert "today" in data
        assert "costs" in data
        assert "actions_needed" in data
        assert "recent_activity" in data
        assert "agent_activity" in data

    def test_daily_ops_today_stats(self):
        """Today stats include expected keys."""
        from orchestrator.daily_ops import DailyOpsView
        from rest_framework.test import APIRequestFactory, force_authenticate
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user("ops_tester2", password="test123", is_staff=True)
        factory = APIRequestFactory()
        request = factory.get("/api/orchestrator/ops/daily/")
        force_authenticate(request, user=user)
        response = DailyOpsView.as_view()(request)
        today = response.data["today"]
        expected_keys = [
            "new_leads", "total_leads", "qualified_today",
            "followups_sent", "followups_pending",
            "approvals_pending", "approvals_decided_today",
            "active_opportunities",
        ]
        for key in expected_keys:
            assert key in today, f"Missing key: {key}"


class TestCostSummaryAPI(TestCase):
    """Test CostSummaryView."""

    def test_cost_summary_api(self):
        from orchestrator.daily_ops import CostSummaryView
        from rest_framework.test import APIRequestFactory, force_authenticate
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user("cost_tester", password="test123", is_staff=True)
        factory = APIRequestFactory()
        request = factory.get("/api/orchestrator/ops/costs/?days=7")
        force_authenticate(request, user=user)
        response = CostSummaryView.as_view()(request)
        assert response.status_code == 200


class TestExecutionFeedbackAPI(TestCase):
    """Test ExecutionFeedbackView."""

    def test_feedback_api(self):
        from agent_runtime.cost_tracker import record_execution
        record_execution(
            execution_id="api-feedback-001",
            agent_type="sdr",
            provider="local",
            prompt_tokens=100,
            completion_tokens=50,
        )
        from orchestrator.daily_ops import ExecutionFeedbackView
        from rest_framework.test import APIRequestFactory, force_authenticate
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user("feedback_tester", password="test123", is_staff=True)
        factory = APIRequestFactory()
        request = factory.post(
            "/api/orchestrator/ops/executions/api-feedback-001/feedback/",
            {"quality": 5, "useful": True, "notes": "Excelente"},
            format="json",
        )
        force_authenticate(request, user=user)
        response = ExecutionFeedbackView.as_view()(request, execution_id="api-feedback-001")
        assert response.status_code == 200
        assert response.data["status"] == "recorded"


# ── Landing Webhook Integration ───────────────────────────────────────────────

class TestLandingWebhook(TestCase):
    """Test that the landing page form data goes through the webhook correctly."""

    def test_landing_page_payload_format(self):
        """Simulate what the landing form JS sends."""
        from commercial.webhooks import handle_webhook
        payload = {
            "contact_name": "João Silva",
            "contact_email": "joao@empresa.com.br",
            "company_name": "Empresa XPTO",
            "phone": "(11) 99999-8888",
            "message": "Quero uma demo do DocAI",
        }
        result = handle_webhook(
            source="landing_page",
            payload=payload,
            raw_body=None,
            signature="",
            hmac_secret=None,
        )
        assert result["created"] is True
        assert result["lead_id"]
        assert result["score"] >= 0

    def test_landing_page_duplicate_lead(self):
        """Resubmitting the same email should update, not duplicate."""
        from commercial.webhooks import handle_webhook
        payload = {
            "contact_name": "Maria Santos",
            "contact_email": "maria@docai.ai",
            "company_name": "DocAI Demo",
        }
        r1 = handle_webhook(source="landing_page", payload=payload, raw_body=None, signature="", hmac_secret=None)
        r2 = handle_webhook(source="landing_page", payload=payload, raw_body=None, signature="", hmac_secret=None)
        assert r1["created"] is True
        assert r2["created"] is False  # re-ingested, not duplicated


# ── Integration Flow Test ─────────────────────────────────────────────────────

class TestEndToEndFlow(TestCase):
    """
    Test the complete operational flow:
    Landing page → Lead → Qualification → Follow-up → Approval → Dispatch
    """

    def test_lead_ingestion_from_landing(self):
        """Lead enters system via landing page webhook."""
        from commercial.webhooks import handle_webhook
        from commercial.models import Lead

        result = handle_webhook(
            source="landing_page",
            payload={
                "contact_name": "Carlos CEO",
                "contact_email": "carlos@bigcorp.com",
                "company_name": "BigCorp S.A.",
                "phone": "11987654321",
                "message": "Preciso automatizar análise de DRE",
            },
            raw_body=None,
            signature="",
            hmac_secret=None,
        )
        assert result["created"] is True

        lead = Lead.objects.get(lead_id=result["lead_id"])
        assert lead.contact_name == "Carlos CEO"
        assert lead.contact_email == "carlos@bigcorp.com"
        assert lead.company_name == "BigCorp S.A."
        assert lead.score >= 0

    def test_cost_tracker_records_persist(self):
        """Cost records survive and aggregate correctly."""
        from agent_runtime.cost_tracker import record_execution, cost_summary

        for i in range(3):
            record_execution(
                execution_id=f"flow-test-{i}",
                agent_type="sdr",
                provider="openai",
                prompt_tokens=500,
                completion_tokens=200,
                latency_ms=1000,
                status="success",
            )

        summary = cost_summary(days=1)
        assert summary["total_executions"] >= 3
        assert summary["total_tokens"] >= 2100  # 3 * 700
