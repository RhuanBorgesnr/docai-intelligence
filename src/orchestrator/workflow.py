"""Simple workflow engine for case state transitions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.db import transaction

from audit.services import write_audit_log
from memory.models import MemorySnapshot
from orchestrator.durable_events import persist_case_event
from orchestrator.enums import CaseState, EventType, WorkflowStatus
from orchestrator.models import Case, CaseEvent


@dataclass(frozen=True)
class TransitionResult:
    previous_state: str
    new_state: str
    changed: bool
    emitted_event_types: list[str]


TRANSITIONS: dict[tuple[str, str], tuple[str, list[str]]] = {
    (CaseState.NEW, EventType.LEAD_RECEIVED): (CaseState.TRIAGE, []),
    (CaseState.TRIAGE, EventType.LEAD_QUALIFIED): (CaseState.QUALIFIED, []),
    (CaseState.QUALIFIED, EventType.DOCUMENT_SAMPLE_REQUESTED): (CaseState.WAITING_DOC_SAMPLE, []),
    (CaseState.WAITING_DOC_SAMPLE, EventType.DOCUMENT_SAMPLE_RECEIVED): (
        CaseState.DOC_SENT_TO_DOCAI,
        [EventType.DOCAI_ANALYSIS_REQUESTED],
    ),
    (CaseState.DOC_SENT_TO_DOCAI, EventType.DOCAI_ANALYSIS_COMPLETED): (CaseState.ANALYSIS_READY, []),
    (CaseState.ANALYSIS_READY, EventType.PROPOSAL_DRAFT_GENERATED): (CaseState.PROPOSAL_DRAFT_READY, []),
    (CaseState.PROPOSAL_DRAFT_READY, EventType.APPROVAL_REQUIRED): (
        CaseState.WAITING_HUMAN_APPROVAL,
        [],
    ),
    (CaseState.WAITING_HUMAN_APPROVAL, EventType.APPROVAL_GRANTED): (
        CaseState.APPROVED_TO_SEND,
        [],
    ),
    (CaseState.WAITING_HUMAN_APPROVAL, EventType.APPROVAL_REJECTED): (CaseState.BLOCKED, []),
}


def _create_snapshot(case: Case) -> None:
    MemorySnapshot.objects.create(
        case=case,
        state=case.state,
        summary=f"Case moved to {case.state}",
        snapshot_data={
            "state": case.state,
            "workflow_status": case.workflow_status,
            "priority": case.priority,
            "updated_at": case.updated_at.isoformat() if case.updated_at else "",
        },
    )


def _emit_followup_events(case: Case, source_event: CaseEvent, event_types: Iterable[str]) -> list[str]:
    emitted: list[str] = []
    for event_type in event_types:
        write_result = persist_case_event(
            case=case,
            event_id=f"{source_event.event_id}:{event_type}",
            event_type=event_type,
            event_version=source_event.event_version,
            source="orchestrator.workflow_engine",
            priority=source_event.priority,
            occurred_at=source_event.occurred_at,
            correlation_id=source_event.correlation_id,
            trace_id=source_event.trace_id,
            tenant_id=case.tenant_id,
            payload={"generated_from": source_event.event_id},
            meta={"system_generated": True},
            causation_id=source_event.event_id,
        )
        emitted.append(write_result.event.event_type)

    return emitted


def apply_transition(event: CaseEvent) -> TransitionResult:
    """Apply one deterministic state transition with row-level lock."""
    with transaction.atomic():
        locked_case = Case.objects.select_for_update().get(pk=event.case_id)
        previous_state = locked_case.state

        if event.event_type == EventType.WORKFLOW_FAILED:
            locked_case.state = CaseState.FAILED
            locked_case.workflow_status = WorkflowStatus.FAILED
            locked_case.save(update_fields=["state", "workflow_status", "updated_at"])
            _create_snapshot(locked_case)
            write_audit_log(
                action="workflow.transitioned",
                case_id=locked_case.id,
                trace_id=event.trace_id,
                correlation_id=event.correlation_id,
                details={"from": previous_state, "to": locked_case.state, "event_type": event.event_type},
            )
            return TransitionResult(previous_state, locked_case.state, True, [])

        transition = TRANSITIONS.get((locked_case.state, event.event_type))
        if not transition:
            write_audit_log(
                action="workflow.transition.skipped",
                case_id=locked_case.id,
                trace_id=event.trace_id,
                correlation_id=event.correlation_id,
                details={"state": locked_case.state, "event_type": event.event_type},
            )
            return TransitionResult(previous_state, locked_case.state, False, [])

        next_state, followup_event_types = transition
        locked_case.state = next_state

        if next_state in {CaseState.WON, CaseState.LOST, CaseState.CLOSED}:
            locked_case.workflow_status = WorkflowStatus.COMPLETED
        elif next_state == CaseState.WAITING_HUMAN_APPROVAL:
            locked_case.workflow_status = WorkflowStatus.WAITING_APPROVAL
        elif next_state in {CaseState.BLOCKED, CaseState.FAILED}:
            locked_case.workflow_status = WorkflowStatus.BLOCKED
        else:
            locked_case.workflow_status = WorkflowStatus.RUNNING

        locked_case.save(update_fields=["state", "workflow_status", "updated_at"])

        _create_snapshot(locked_case)
        emitted_events = _emit_followup_events(locked_case, event, followup_event_types)

        write_audit_log(
            action="workflow.transitioned",
            case_id=locked_case.id,
            trace_id=event.trace_id,
            correlation_id=event.correlation_id,
            details={
                "from": previous_state,
                "to": locked_case.state,
                "event_type": event.event_type,
                "emitted_events": emitted_events,
            },
        )

        return TransitionResult(previous_state, locked_case.state, True, emitted_events)
