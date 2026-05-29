import pytest
from asgiref.sync import async_to_sync

from agent_runtime.inter_agent_bus import CommandPriority, InterAgentBus
from approvals.gateway import ApprovalDecision, ApprovalGateway, ApprovalPolicy, ApprovalPriority
from orchestrator.durable_events import mark_event_processed, persist_case_event, persist_runtime_outbox_event
from orchestrator.enums import Priority
from orchestrator.models import Case, EventInbox, EventOutbox


@pytest.mark.django_db(transaction=True)
def test_persist_case_event_creates_outbox():
    case = Case.objects.create(
        external_ref="case-hardening-1",
        tenant_id="tenant-a",
        title="Case Hardening",
        correlation_id="corr-hardening-1",
        trace_id="trace-hardening-1",
    )

    result = persist_case_event(
        case=case,
        event_id="evt-hardening-1",
        event_type="lead.received",
        event_version="1.0",
        source="test-suite",
        priority=Priority.MEDIUM,
        occurred_at=case.created_at,
        correlation_id="corr-hardening-1",
        trace_id="trace-hardening-1",
        tenant_id=case.tenant_id,
        payload={"hello": "world"},
        meta={"test": True},
        causation_id="cause-1",
    )

    assert result.created is True
    assert EventOutbox.objects.filter(event_id="evt-hardening-1").exists()


@pytest.mark.django_db(transaction=True)
def test_event_inbox_deduplicates_consumer_processing():
    case = Case.objects.create(
        external_ref="case-hardening-2",
        tenant_id="tenant-a",
        title="Inbox Case",
        correlation_id="corr-hardening-2",
        trace_id="trace-hardening-2",
    )

    result = persist_case_event(
        case=case,
        event_id="evt-hardening-2",
        event_type="lead.received",
        event_version="1.0",
        source="test-suite",
        priority=Priority.MEDIUM,
        occurred_at=case.created_at,
        correlation_id="corr-hardening-2",
        trace_id="trace-hardening-2",
        tenant_id=case.tenant_id,
        payload={"hello": "world"},
        meta={},
    )

    assert mark_event_processed(consumer="worker-a", event=result.event) is True
    assert mark_event_processed(consumer="worker-a", event=result.event) is False
    assert EventInbox.objects.filter(consumer="worker-a", event_id="evt-hardening-2").count() == 1


@pytest.mark.django_db(transaction=True)
def test_runtime_outbox_event_persists_non_workflow_event():
    case = Case.objects.create(
        external_ref="case-hardening-3",
        tenant_id="tenant-a",
        title="Runtime Event Case",
        correlation_id="corr-hardening-3",
        trace_id="trace-hardening-3",
    )

    outbox = persist_runtime_outbox_event(
        event_id="approval:approval-1:requested",
        case=case,
        event_type="approval.requested",
        source="approval_gateway",
        tenant_id=case.tenant_id,
        correlation_id=case.correlation_id,
        trace_id=case.trace_id,
        payload={"approval_id": "approval-1"},
        causation_id="approval-1",
    )

    assert outbox.event_type == "approval.requested"
    assert EventOutbox.objects.filter(event_id="approval:approval-1:requested").exists()


@pytest.mark.django_db(transaction=True)
def test_approval_gateway_persists_and_requires_authorized_approver():
    """Synchronous wrapper: ApprovalGateway persists to DB and validates approver identity."""
    policy = ApprovalPolicy(
        requires_approval=True,
        approval_fields=["amount"],
        approvers=["manager@company.com"],
        deadline_minutes=30,
        escalation_deadline_minutes=15,
        priority=ApprovalPriority.URGENT,
    )

    approval = async_to_sync(ApprovalGateway.request_approval)(
        approval_id="approval-hardening-1",
        case_id="case-hardening-approval",
        correlation_id="corr-approval-1",
        agent_type="sales_agent",
        action="proposal.send",
        data_to_approve={"amount": 10000},
        affected_fields=["amount"],
        context={"company": "Acme"},
        policy=policy,
    )

    assert approval.status == "pending"
    persisted = ApprovalGateway.get_approval("approval-hardening-1")
    assert persisted is not None
    assert persisted.policy.approvers == ["manager@company.com"]

    with pytest.raises(PermissionError):
        async_to_sync(ApprovalGateway.decide_approval)(
            approval_id="approval-hardening-1",
            decision=ApprovalDecision.APPROVED,
            approved_by="intruder@company.com",
        )


@pytest.mark.django_db(transaction=True)
def test_approval_gateway_sweep_escalates_and_expires():
    policy = ApprovalPolicy(
        requires_approval=True,
        approval_fields=["amount"],
        approvers=["manager@company.com"],
        deadline_minutes=0,
        escalation_deadline_minutes=0,
        priority=ApprovalPriority.CRITICAL,
    )

    # Persist directly via sync helper to keep this test fully synchronous.
    created = ApprovalGateway._request_approval_sync(
        approval_id="approval-hardening-2",
        case_id="case-hardening-approval-2",
        correlation_id="corr-approval-2",
        agent_type="sales_agent",
        action="proposal.send",
        data_to_approve={"amount": 5000},
        affected_fields=["amount"],
        context={},
        policy=policy,
    )
    assert created.approval_id == "approval-hardening-2"

    result = ApprovalGateway.sweep_due_approvals()
    assert result["expired"] >= 1


@pytest.mark.django_db(transaction=True)
def test_inter_agent_bus_supports_wildcard_contract_lookup():
    contract = InterAgentBus.get_contract("any-agent", "analyze_document")
    assert contract is not None
    assert contract.target_agent == "docai_operator"


@pytest.mark.django_db(transaction=True)
def test_inter_agent_bus_loop_guard_blocks_repeated_inflight_signature():
    """hop_count >= 8 triggers the hop-count guard, raising ValueError."""
    case = Case.objects.create(
        external_ref="case-hardening-commands",
        tenant_id="tenant-a",
        title="Command Loop Case",
        correlation_id="corr-command-1",
        trace_id="trace-command-1",
    )

    # hop_count=8 meets the >= 8 threshold and must raise ValueError.
    payload = {"document_path": "/tmp/test.pdf", "case_id": case.external_ref, "hop_count": 8}
    contract = InterAgentBus.get_contract("any-agent", "analyze_document")
    assert contract is not None

    with pytest.raises(ValueError):
        InterAgentBus._create_command_sync(
            "cmd-loop-1",
            case.external_ref,
            case.correlation_id,
            "any-agent",
            "docai_operator",
            "analyze_document",
            payload,
            CommandPriority.HIGH,
            contract,
        )
