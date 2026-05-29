"""Services for event ingestion and case upsert."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.services import write_audit_log
from orchestrator.durable_events import persist_case_event
from orchestrator.enums import CaseState, Priority, WorkflowStatus
from orchestrator.models import Case, CaseEvent


@dataclass(frozen=True)
class IngestionResult:
    event: CaseEvent
    created: bool


def _resolve_case(payload: dict[str, Any], correlation_id: str, trace_id: str, tenant_id: str, priority: str) -> Case:
    external_ref = payload.get("case_id") or payload.get("external_ref")
    title = payload.get("title", "")

    if external_ref:
        case, created = Case.objects.get_or_create(
            external_ref=external_ref,
            defaults={
                "tenant_id": tenant_id,
                "title": title,
                "state": CaseState.NEW,
                "workflow_status": WorkflowStatus.RUNNING,
                "priority": priority,
                "correlation_id": correlation_id,
                "trace_id": trace_id,
            },
        )
        if not created:
            changed = False
            if trace_id and case.trace_id != trace_id:
                case.trace_id = trace_id
                changed = True
            if correlation_id and case.correlation_id != correlation_id:
                case.correlation_id = correlation_id
                changed = True
            if changed:
                case.save(update_fields=["trace_id", "correlation_id", "updated_at"])
        return case

    return Case.objects.create(
        tenant_id=tenant_id,
        title=title,
        state=CaseState.NEW,
        workflow_status=WorkflowStatus.RUNNING,
        priority=priority,
        correlation_id=correlation_id,
        trace_id=trace_id,
    )


def ingest_event(*, data: dict[str, Any]) -> IngestionResult:
    """Persist event idempotently and attach it to a case."""
    event_id = data["event_id"]
    payload = data.get("payload") or {}
    meta = data.get("meta") or {}
    correlation_id = data.get("correlation_id") or event_id
    trace_id = meta.get("trace_id") or data.get("trace_id") or correlation_id
    tenant_id = data.get("tenant_id", "default")
    priority = data.get("priority", Priority.MEDIUM)
    occurred_at = data.get("occurred_at") or timezone.now()

    try:
        existing = CaseEvent.objects.select_related("case").get(event_id=event_id)
        return IngestionResult(event=existing, created=False)
    except CaseEvent.DoesNotExist:
        pass

    with transaction.atomic():
        case = _resolve_case(payload, correlation_id, trace_id, tenant_id, priority)
        try:
            write_result = persist_case_event(
                case=case,
                event_id=event_id,
                event_type=data["event_type"],
                event_version=data.get("event_version", "1.0"),
                source=data.get("source", "unknown"),
                priority=priority,
                occurred_at=occurred_at,
                correlation_id=correlation_id,
                trace_id=trace_id,
                tenant_id=tenant_id,
                payload=payload,
                meta=meta,
                causation_id=meta.get("causation_id", ""),
            )
            event = write_result.event
            write_audit_log(
                action="event.received",
                case_id=case.id,
                trace_id=trace_id,
                correlation_id=correlation_id,
                details={"event_id": event_id, "event_type": event.event_type},
            )

            # Broadcast real-time event via WebSocket
            try:
                from orchestrator.ws_broadcasts import sync_broadcast_case_event
                sync_broadcast_case_event(
                    case_id=case.id,
                    event_type=event.event_type,
                    payload={
                        "event_id": event_id,
                        "case_state": case.state,
                        "priority": str(case.priority),
                        "tenant_id": tenant_id,
                    },
                )
            except Exception:
                pass  # WebSocket broadcast is best-effort

            return IngestionResult(event=event, created=write_result.created)
        except IntegrityError:
            event = CaseEvent.objects.select_related("case").get(event_id=event_id)
            return IngestionResult(event=event, created=False)
