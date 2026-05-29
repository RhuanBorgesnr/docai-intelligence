"""
Sprint 3 – Bloco 4: Jarvis Executive Agent Integration Tests.

Tests:
- Jarvis tools (get_case_summary, list_pending_approvals, view_metrics, etc.)
- Routing table & JarvisAgent.evaluate_case deterministic routing
- JarvisAgent.dispatch (route + escalate)
- Workflow hook → Jarvis trigger
- Executive briefing generation
- Specialist agent instantiation & registry
- Celery task wiring
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone as dj_timezone

from approvals.models import Approval
from notifications.models import Notification
from orchestrator.enums import ApprovalStatus, Priority
from orchestrator.jarvis_agent import (
    ROUTING_TABLE,
    TERMINAL_STATES,
    WAITING_STATES,
    JarvisAgent,
    JarvisDecision,
)
from orchestrator.jarvis_tools import (
    TOOL_REGISTRY,
    execute_tool,
    get_case_summary,
    list_pending_approvals,
    route_to_agent,
    send_notification,
    view_metrics,
)
from orchestrator.models import Case, CaseEvent
from orchestrator.specialist_agents import (
    SPECIALIST_REGISTRY,
    AgentCaseContext,
    DocAIOperatorAgent,
    IntakeAgent,
    SDRAgent,
    SalesAgent,
    _build_user_message,
    get_specialist,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _case(ref, state="new", tenant="t1", **kw):
    return Case.objects.create(
        external_ref=ref,
        tenant_id=tenant,
        title=kw.get("title", f"Case {ref}"),
        state=state,
        priority=kw.get("priority", Priority.MEDIUM),
        correlation_id=f"corr-{ref}",
        trace_id=f"trace-{ref}",
    )


def _event(case, event_type="lead.received"):
    return CaseEvent.objects.create(
        case=case,
        event_type=event_type,
        payload={"source": "test"},
        correlation_id=case.correlation_id,
        trace_id=case.trace_id,
        occurred_at=dj_timezone.now(),
    )


def _approval(case, status="pending", **kw):
    import uuid
    return Approval.objects.create(
        approval_id=str(uuid.uuid4()),
        case=case,
        requested_by_agent="test",
        approval_type="proposal",
        status=status,
        tenant_id=case.tenant_id,
        deadline_at=kw.get("deadline_at", dj_timezone.now() + timedelta(days=1)),
        correlation_id=case.correlation_id,
        trace_id=case.trace_id,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  A. TOOL REGISTRY & TOOL FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestJarvisTools:
    """Tests for jarvis_tools.py functions."""

    def test_tool_registry_has_all_tools(self):
        expected = {
            "get_case_summary",
            "list_pending_approvals",
            "view_metrics",
            "send_notification",
            "route_to_agent",
            "find_similar_cases",
        }
        assert set(TOOL_REGISTRY.keys()) == expected

    def test_get_case_summary(self):
        case = _case("TOOL-1", state="qualified")
        _event(case, "lead.qualified")
        _approval(case)

        result = get_case_summary(case.id)
        assert result["state"] == "qualified"
        assert result["external_ref"] == "TOOL-1"
        assert len(result["recent_events"]) >= 1
        assert len(result["pending_approvals"]) >= 1

    def test_get_case_summary_not_found(self):
        result = get_case_summary(999999)
        assert "error" in result

    def test_list_pending_approvals(self):
        case = _case("TOOL-2")
        _approval(case, status="pending")
        _approval(case, status="approved")

        result = list_pending_approvals()
        assert result["count"] >= 1
        pending = [a for a in result["approvals"] if a["case_id"] == case.id]
        assert len(pending) == 1

    def test_list_pending_approvals_overdue_flag(self):
        case = _case("TOOL-3")
        _approval(case, status="pending", deadline_at=dj_timezone.now() - timedelta(hours=1))

        result = list_pending_approvals()
        overdue = [a for a in result["approvals"] if a.get("overdue")]
        assert len(overdue) >= 1

    def test_view_metrics(self):
        _case("TOOL-4", state="new")
        result = view_metrics()
        assert "pipeline" in result
        assert "throughput" in result
        assert "notifications" in result
        assert "health" in result

    def test_send_notification(self):
        case = _case("TOOL-5")
        result = send_notification(
            case_id=case.id,
            channel="email",
            recipient="test@example.com",
            message="Hello",
        )
        assert result["status"] == "queued"
        assert Notification.objects.filter(case=case, channel="email").exists()

    @patch("agent_runtime.inter_agent_bus.InterAgentBus")
    def test_route_to_agent(self, mock_bus_cls):
        mock_bus = MagicMock()
        mock_bus.send_command.return_value = "cmd-42"
        mock_bus_cls.return_value = mock_bus

        case = _case("TOOL-ROUTE")
        result = route_to_agent(case_id=case.id, target_agent="sdr", instruction="Go")
        assert result["status"] == "dispatched"
        assert result["target_agent"] == "sdr"

    def test_execute_tool_dispatches(self):
        case = _case("TOOL-6")
        result = execute_tool("get_case_summary", case_id=case.id)
        assert result["external_ref"] == "TOOL-6"

    def test_execute_tool_unknown(self):
        result = execute_tool("nonexistent_tool")
        assert "error" in result


# ══════════════════════════════════════════════════════════════════════════════
#  B. JARVIS AGENT — ROUTING
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestJarvisRouting:
    """Tests for JarvisAgent deterministic routing logic."""

    def test_routing_table_covers_expected_states(self):
        assert "new" in ROUTING_TABLE
        assert "qualified" in ROUTING_TABLE
        assert "doc_sent_to_docai" in ROUTING_TABLE
        assert "proposal_draft_ready" in ROUTING_TABLE

    def test_evaluate_routes_new_to_intake(self):
        case = _case("JAR-1", state="new")
        jarvis = JarvisAgent()
        decision = jarvis.evaluate_case(case.id)
        assert decision.action == "route"
        assert decision.target_agent == "intake"

    def test_evaluate_routes_qualified_to_sdr(self):
        case = _case("JAR-2", state="qualified")
        decision = JarvisAgent().evaluate_case(case.id)
        assert decision.action == "route"
        assert decision.target_agent == "sdr"

    def test_evaluate_routes_doc_to_docai(self):
        case = _case("JAR-3", state="doc_sent_to_docai")
        decision = JarvisAgent().evaluate_case(case.id)
        assert decision.action == "route"
        assert decision.target_agent == "docai"

    def test_evaluate_routes_proposal_to_sales(self):
        case = _case("JAR-4", state="proposal_draft_ready")
        decision = JarvisAgent().evaluate_case(case.id)
        assert decision.action == "route"
        assert decision.target_agent == "sales"

    def test_evaluate_terminal_skips(self):
        for state in TERMINAL_STATES:
            case = _case(f"JAR-TERM-{state}", state=state)
            decision = JarvisAgent().evaluate_case(case.id)
            assert decision.action == "skip"

    def test_evaluate_waiting_approval_waits(self):
        case = _case("JAR-WAIT", state="waiting_human_approval")
        _approval(case, status="pending")  # not overdue
        decision = JarvisAgent().evaluate_case(case.id)
        assert decision.action == "wait"

    def test_evaluate_overdue_approval_escalates(self):
        case = _case("JAR-ESC", state="waiting_human_approval")
        _approval(case, status="pending", deadline_at=dj_timezone.now() - timedelta(hours=2))
        decision = JarvisAgent().evaluate_case(case.id)
        assert decision.action == "escalate"

    def test_evaluate_case_not_found(self):
        decision = JarvisAgent().evaluate_case(999999)
        assert decision.action == "skip"
        assert "not found" in decision.reason.lower()


# ══════════════════════════════════════════════════════════════════════════════
#  C. JARVIS AGENT — DISPATCH
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestJarvisDispatch:
    """Tests for dispatch execution."""

    @patch("agent_runtime.inter_agent_bus.InterAgentBus")
    def test_dispatch_route(self, mock_bus_cls):
        mock_bus = MagicMock()
        mock_bus.send_command.return_value = MagicMock(id=1)
        mock_bus_cls.return_value = mock_bus

        case = _case("DIS-1", state="new")
        jarvis = JarvisAgent()
        decision = jarvis.evaluate_case(case.id)
        result = jarvis.dispatch(decision)
        assert result["status"] == "dispatched"
        assert result["target_agent"] == "intake"

    def test_dispatch_escalate_creates_notification(self):
        case = _case("DIS-2", state="waiting_human_approval")
        _approval(case, status="pending", deadline_at=dj_timezone.now() - timedelta(hours=1))
        jarvis = JarvisAgent()
        decision = jarvis.evaluate_case(case.id)
        result = jarvis.dispatch(decision)
        assert result["status"] == "queued"
        assert Notification.objects.filter(case=case, channel="email").exists()

    @patch("agent_runtime.inter_agent_bus.InterAgentBus")
    def test_process_event_full_cycle(self, mock_bus_cls):
        mock_bus = MagicMock()
        mock_bus.send_command.return_value = MagicMock(id=1)
        mock_bus_cls.return_value = mock_bus

        case = _case("DIS-3", state="qualified")
        result = JarvisAgent().process_event(case.id)
        assert result["decision"]["action"] == "route"
        assert result["decision"]["target_agent"] == "sdr"
        assert "dispatch" in result


# ══════════════════════════════════════════════════════════════════════════════
#  D. BRIEFING
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestJarvisBriefing:
    """Tests for executive briefing generation."""

    def test_briefing_structure(self):
        _case("BRF-1", state="new")
        _case("BRF-2", state="qualified")

        briefing = JarvisAgent().generate_briefing()
        assert "generated_at" in briefing
        assert "summary" in briefing
        assert "alerts" in briefing
        assert "pipeline_breakdown" in briefing
        assert briefing["summary"]["active_cases"] >= 2

    def test_briefing_detects_overdue_approvals(self):
        case = _case("BRF-3", state="waiting_human_approval")
        _approval(case, status="pending", deadline_at=dj_timezone.now() - timedelta(hours=1))

        briefing = JarvisAgent().generate_briefing()
        assert briefing["summary"]["overdue_approvals"] >= 1
        assert any("vencida" in a for a in briefing["alerts"])


# ══════════════════════════════════════════════════════════════════════════════
#  E. SPECIALIST AGENTS
# ══════════════════════════════════════════════════════════════════════════════

class TestSpecialistAgents:
    """Tests for specialist agent classes."""

    def test_registry_has_all_specialists(self):
        expected = {"intake", "sdr", "sales", "docai", "analyst"}
        assert set(SPECIALIST_REGISTRY.keys()) == expected

    def test_get_specialist_instantiates(self):
        agent = get_specialist("intake")
        assert isinstance(agent, IntakeAgent)

    def test_get_specialist_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown specialist"):
            get_specialist("unknown_agent")

    def test_build_user_message_has_case_info(self):
        ctx = AgentCaseContext(
            case_id=1,
            external_ref="TEST-1",
            title="Test Case",
            state="new",
            priority="medium",
            instruction="Classify this lead",
            rag_context="Company ABC...",
        )
        msg = _build_user_message(ctx, "Intake Agent")
        assert "TEST-1" in msg
        assert "Test Case" in msg
        assert "Intake Agent" in msg
        assert "Classify this lead" in msg
        assert "Company ABC" in msg

    def test_each_specialist_has_correct_agent_type(self):
        from agent_runtime.prompt_registry import AgentType

        assert IntakeAgent.agent_type == AgentType.INTAKE
        assert SDRAgent.agent_type == AgentType.SDR
        assert SalesAgent.agent_type == AgentType.SALES
        assert DocAIOperatorAgent.agent_type == AgentType.DOCAI_OPERATOR


# ══════════════════════════════════════════════════════════════════════════════
#  F. CELERY TASKS (WIRING)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestJarvisTasks:
    """Tests for Celery task wiring."""

    @patch("orchestrator.jarvis_agent.JarvisAgent.process_event")
    def test_jarvis_evaluate_case_task(self, mock_process):
        mock_process.return_value = {"decision": {"action": "skip"}}
        from orchestrator.tasks import jarvis_evaluate_case

        result = jarvis_evaluate_case(case_id=1)
        mock_process.assert_called_once_with(1)
        assert result["decision"]["action"] == "skip"

    @patch("orchestrator.jarvis_agent.JarvisAgent.generate_briefing")
    def test_jarvis_briefing_task(self, mock_briefing):
        mock_briefing.return_value = {"alert_count": 0, "summary": {"active_cases": 5}}
        from orchestrator.tasks import jarvis_generate_briefing

        result = jarvis_generate_briefing(tenant_id="demo")
        mock_briefing.assert_called_once_with(tenant_id="demo")
        assert result["summary"]["active_cases"] == 5

    @patch("orchestrator.tasks.jarvis_evaluate_case")
    def test_workflow_transition_triggers_jarvis(self, mock_jarvis_task):
        """After a successful workflow transition, Jarvis should be triggered."""
        mock_delay = MagicMock()
        mock_jarvis_task.delay = mock_delay

        case = _case("WF-JAR", state="new")
        event = _event(case, "lead.received")

        from orchestrator.tasks import execute_workflow_transition

        execute_workflow_transition(event.id)

        # Transition new + lead.received → triage (changed=True) → triggers Jarvis
        mock_delay.assert_called_once_with(case.id)
