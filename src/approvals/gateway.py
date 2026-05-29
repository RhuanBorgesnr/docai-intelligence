"""Durable approval gateway with persistent lifecycle and scheduler-driven monitoring."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from asgiref.sync import async_to_sync, sync_to_async
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from approvals.models import Approval as ApprovalRecord
from orchestrator.durable_events import persist_runtime_outbox_event
from orchestrator.enums import ApprovalStatus
from orchestrator.models import Case

logger = logging.getLogger(__name__)


class ApprovalDecision(str, Enum):
    """Decisões possíveis em uma aprovação."""

    APPROVED = "approved"
    REJECTED = "rejected"
    REQUEST_CHANGES = "request_changes"
    EXPIRED = "expired"
    ESCALATED = "escalated"


class ApprovalPriority(str, Enum):
    """Prioridade de uma aprovação."""

    ROUTINE = "routine"
    URGENT = "urgent"
    CRITICAL = "critical"


@dataclass
class ApprovalPolicy:
    """Política de aprovação para diferentes ações."""

    requires_approval: bool
    approval_fields: List[str]
    approvers: List[str]
    deadline_minutes: int
    escalation_deadline_minutes: int
    priority: ApprovalPriority

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requires_approval": self.requires_approval,
            "approval_fields": self.approval_fields,
            "approvers": self.approvers,
            "deadline_minutes": self.deadline_minutes,
            "escalation_deadline_minutes": self.escalation_deadline_minutes,
            "priority": self.priority.value,
        }


@dataclass
class ApprovalRequest:
    """Representação de domínio de uma aprovação persistida."""

    approval_id: str
    case_id: str
    correlation_id: str
    agent_type: str
    action: str
    data_to_approve: Dict[str, Any]
    affected_fields: List[str]
    context: Dict[str, Any]
    policy: ApprovalPolicy
    status: str = "pending"
    created_at: datetime | None = None
    deadline_at: datetime | None = None
    escalation_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    decision_comment: str | None = None
    escalated_to: List[str] | None = None
    escalation_reason: str | None = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = timezone.now()
        if self.deadline_at is None:
            self.deadline_at = self.created_at + timedelta(minutes=self.policy.deadline_minutes)
        if self.escalation_at is None:
            self.escalation_at = self.created_at + timedelta(minutes=self.policy.escalation_deadline_minutes)
        if self.escalated_to is None:
            self.escalated_to = []

    @property
    def is_expired(self) -> bool:
        return self.status in {ApprovalStatus.PENDING, ApprovalStatus.ESCALATED} and timezone.now() > self.deadline_at

    @property
    def should_escalate(self) -> bool:
        return (
            self.status == ApprovalStatus.PENDING
            and timezone.now() > self.escalation_at
            and not self.escalated_to
        )

    @property
    def time_remaining_minutes(self) -> int:
        delta = self.deadline_at - timezone.now()
        return int(delta.total_seconds() / 60)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "case_id": self.case_id,
            "correlation_id": self.correlation_id,
            "agent_type": self.agent_type,
            "action": self.action,
            "data_to_approve": self.data_to_approve,
            "affected_fields": self.affected_fields,
            "context": self.context,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
            "escalation_at": self.escalation_at.isoformat() if self.escalation_at else None,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "decision_comment": self.decision_comment,
            "escalated_to": self.escalated_to,
            "escalation_reason": self.escalation_reason,
            "time_remaining_minutes": self.time_remaining_minutes,
            "is_expired": self.is_expired,
        }


class ApprovalGateway:
    """Gateway centralizado para gerenciar aprovações com persistência durável."""

    _policies: Dict[str, ApprovalPolicy] = {}

    @classmethod
    def register_policy(cls, action_name: str, policy: ApprovalPolicy):
        cls._policies[action_name] = policy
        logger.info("Política de aprovação registrada para '%s'", action_name)

    @classmethod
    def get_policy(cls, action_name: str) -> Optional[ApprovalPolicy]:
        return cls._policies.get(action_name)

    @classmethod
    async def request_approval(
        cls,
        approval_id: str,
        case_id: str,
        correlation_id: str,
        agent_type: str,
        action: str,
        data_to_approve: Dict[str, Any],
        affected_fields: List[str],
        context: Dict[str, Any],
        policy: Optional[ApprovalPolicy] = None,
    ) -> ApprovalRequest:
        policy = policy or cls.get_policy(action) or ApprovalPolicy(
            requires_approval=True,
            approval_fields=affected_fields,
            approvers=["admin@company.com"],
            deadline_minutes=60,
            escalation_deadline_minutes=30,
            priority=ApprovalPriority.ROUTINE,
        )
        approval = await sync_to_async(cls._request_approval_sync, thread_sensitive=True)(
            approval_id,
            case_id,
            correlation_id,
            agent_type,
            action,
            data_to_approve,
            affected_fields,
            context,
            policy,
        )
        await cls._emit_approval_requested_event(approval)
        return approval

    @classmethod
    def _request_approval_sync(
        cls,
        approval_id: str,
        case_id: str,
        correlation_id: str,
        agent_type: str,
        action: str,
        data_to_approve: Dict[str, Any],
        affected_fields: List[str],
        context: Dict[str, Any],
        policy: ApprovalPolicy,
    ) -> ApprovalRequest:
        case = cls._resolve_case(case_id=case_id, correlation_id=correlation_id)
        now = timezone.now()
        payload = {
            "action": action,
            "agent_type": agent_type,
            "data_to_approve": data_to_approve,
            "context": context,
        }
        with transaction.atomic():
            record, _ = ApprovalRecord.objects.update_or_create(
                approval_id=approval_id,
                defaults={
                    "case": case,
                    "approval_type": action,
                    "status": ApprovalStatus.PENDING,
                    "requested_by_agent": agent_type,
                    "tenant_id": case.tenant_id,
                    "correlation_id": correlation_id,
                    "trace_id": correlation_id,
                    "deadline_at": now + timedelta(minutes=policy.deadline_minutes),
                    "escalation_at": now + timedelta(minutes=policy.escalation_deadline_minutes),
                    "approvers": policy.approvers,
                    "approval_fields": affected_fields,
                    "policy_snapshot": policy.to_dict(),
                    "payload": payload,
                    "summary": action,
                    "escalated_to": [],
                    "escalation_reason": "",
                    "decision_comment": "",
                    "decided_at": None,
                    "decided_by": None,
                },
            )
        return cls._to_domain_request(record)

    @classmethod
    async def decide_approval(
        cls,
        approval_id: str,
        decision: ApprovalDecision,
        approved_by: str,
        comment: Optional[str] = None,
    ) -> ApprovalRequest:
        approval = await sync_to_async(cls._decide_approval_sync, thread_sensitive=True)(
            approval_id,
            decision,
            approved_by,
            comment,
        )
        if decision == ApprovalDecision.APPROVED:
            await cls._emit_approval_granted_event(approval)
        elif decision == ApprovalDecision.REJECTED:
            await cls._emit_approval_rejected_event(approval)
        elif decision == ApprovalDecision.REQUEST_CHANGES:
            await cls._emit_approval_changes_requested_event(approval)
        return approval

    @classmethod
    def _decide_approval_sync(
        cls,
        approval_id: str,
        decision: ApprovalDecision,
        approved_by: str,
        comment: Optional[str],
    ) -> ApprovalRequest:
        with transaction.atomic():
            record = ApprovalRecord.objects.select_for_update().select_related("case").get(approval_id=approval_id)
            if record.status not in {ApprovalStatus.PENDING, ApprovalStatus.ESCALATED}:
                raise ValueError(f"Aprovação {approval_id} já foi {record.status}")
            authorized_approvers = set(record.approvers or []) | set(record.escalated_to or [])
            if authorized_approvers and approved_by not in authorized_approvers:
                raise PermissionError(f"Aprovador não autorizado: {approved_by}")
            user = cls._resolve_user(approved_by)
            record.status = decision.value
            record.decided_at = timezone.now()
            record.decision_comment = comment or ""
            record.decided_by = user
            updated_payload = dict(record.payload or {})
            updated_payload["decision_actor"] = approved_by
            record.payload = updated_payload
            record.save(update_fields=["status", "decided_at", "decision_comment", "decided_by", "payload"])
            return cls._to_domain_request(record)

    @classmethod
    async def escalate_approval(
        cls,
        approval_id: str,
        escalate_to: List[str],
        reason: str,
    ) -> ApprovalRequest:
        approval = await sync_to_async(cls._escalate_approval_sync, thread_sensitive=True)(approval_id, escalate_to, reason)
        await cls._emit_approval_escalated_event(approval)
        return approval

    @classmethod
    def _escalate_approval_sync(cls, approval_id: str, escalate_to: List[str], reason: str) -> ApprovalRequest:
        with transaction.atomic():
            record = ApprovalRecord.objects.select_for_update().select_related("case").get(approval_id=approval_id)
            if record.status not in {ApprovalStatus.PENDING, ApprovalStatus.ESCALATED}:
                return cls._to_domain_request(record)
            merged = sorted(set((record.escalated_to or []) + list(escalate_to)))
            record.escalated_to = merged
            record.escalation_reason = reason
            record.status = ApprovalStatus.ESCALATED
            record.save(update_fields=["escalated_to", "escalation_reason", "status"])
            return cls._to_domain_request(record)

    @classmethod
    async def expire_approval(cls, approval_id: str) -> ApprovalRequest:
        approval = await sync_to_async(cls._expire_approval_sync, thread_sensitive=True)(approval_id)
        await cls._emit_approval_expired_event(approval)
        return approval

    @classmethod
    def _expire_approval_sync(cls, approval_id: str) -> ApprovalRequest:
        with transaction.atomic():
            record = ApprovalRecord.objects.select_for_update().select_related("case").get(approval_id=approval_id)
            if record.status not in {ApprovalStatus.PENDING, ApprovalStatus.ESCALATED}:
                return cls._to_domain_request(record)
            record.status = ApprovalStatus.EXPIRED
            record.decided_at = timezone.now()
            record.save(update_fields=["status", "decided_at"])
            return cls._to_domain_request(record)

    @classmethod
    def get_approval(cls, approval_id: str) -> Optional[ApprovalRequest]:
        record = ApprovalRecord.objects.select_related("case").filter(approval_id=approval_id).first()
        return cls._to_domain_request(record) if record else None

    @classmethod
    def list_pending_approvals(cls, approver_email: Optional[str] = None) -> List[ApprovalRequest]:
        records = list(
            ApprovalRecord.objects.select_related("case")
            .filter(status__in=[ApprovalStatus.PENDING, ApprovalStatus.ESCALATED])
            .order_by("deadline_at")
        )
        approvals = [cls._to_domain_request(record) for record in records]
        if approver_email:
            approvals = [
                approval
                for approval in approvals
                if approver_email in approval.policy.approvers or approver_email in approval.escalated_to
            ]
        return approvals

    @classmethod
    def sweep_due_approvals(cls) -> Dict[str, int]:
        now = timezone.now()
        escalated = 0
        expired = 0
        records = ApprovalRecord.objects.select_related("case").filter(
            status__in=[ApprovalStatus.PENDING, ApprovalStatus.ESCALATED],
        )
        for record in records:
            if record.status == ApprovalStatus.PENDING and record.escalation_at and now >= record.escalation_at and not record.escalated_to:
                approval = cls._escalate_approval_sync(
                    approval_id=record.approval_id,
                    escalate_to=record.approvers or [],
                    reason="Prazo de aprovação vencendo em breve",
                )
                async_to_sync(cls._emit_approval_escalated_event)(approval)
                escalated += 1
            if record.deadline_at and now >= record.deadline_at:
                approval = cls._expire_approval_sync(record.approval_id)
                async_to_sync(cls._emit_approval_expired_event)(approval)
                expired += 1
        return {"escalated": escalated, "expired": expired}

    @classmethod
    def _resolve_case(cls, case_id: str, correlation_id: str) -> Case:
        if case_id.isdigit():
            case = Case.objects.filter(pk=int(case_id)).first()
            if case:
                return case
        case = Case.objects.filter(external_ref=case_id).first()
        if case:
            return case
        return Case.objects.create(
            external_ref=case_id,
            tenant_id="default",
            title=case_id,
            correlation_id=correlation_id,
            trace_id=correlation_id,
        )

    @classmethod
    def _resolve_user(cls, approver_identity: str):
        user_model = get_user_model()
        return user_model.objects.filter(email=approver_identity).first() or user_model.objects.filter(username=approver_identity).first()

    @classmethod
    def _to_domain_request(cls, record: ApprovalRecord) -> ApprovalRequest:
        policy_data = record.policy_snapshot or {}
        payload = record.payload or {}
        actor = payload.get("decision_actor")
        approved_by = actor or (getattr(record.decided_by, "email", None) if record.decided_by_id else None)
        policy = ApprovalPolicy(
            requires_approval=policy_data.get("requires_approval", True),
            approval_fields=policy_data.get("approval_fields", record.approval_fields or []),
            approvers=policy_data.get("approvers", record.approvers or []),
            deadline_minutes=policy_data.get("deadline_minutes", 60),
            escalation_deadline_minutes=policy_data.get("escalation_deadline_minutes", 30),
            priority=ApprovalPriority(policy_data.get("priority", ApprovalPriority.ROUTINE.value)),
        )
        return ApprovalRequest(
            approval_id=record.approval_id,
            case_id=record.case.external_ref or str(record.case_id),
            correlation_id=record.correlation_id,
            agent_type=payload.get("agent_type", record.requested_by_agent),
            action=payload.get("action", record.approval_type),
            data_to_approve=payload.get("data_to_approve", {}),
            affected_fields=record.approval_fields or [],
            context=payload.get("context", {}),
            policy=policy,
            status=record.status,
            created_at=record.requested_at,
            deadline_at=record.deadline_at,
            escalation_at=record.escalation_at,
            approved_by=approved_by,
            approved_at=record.decided_at,
            decision_comment=record.decision_comment,
            escalated_to=record.escalated_to or [],
            escalation_reason=record.escalation_reason,
        )

    @classmethod
    async def _emit_runtime_event(cls, approval: ApprovalRequest, event_suffix: str) -> None:
        await sync_to_async(cls._emit_runtime_event_sync, thread_sensitive=True)(approval, event_suffix)
        logger.info("Evento durável emitido: approval.%s", event_suffix)

    @classmethod
    def _emit_runtime_event_sync(cls, approval: ApprovalRequest, event_suffix: str) -> None:
        case = Case.objects.filter(external_ref=approval.case_id).first()
        if not case and approval.case_id.isdigit():
            case = Case.objects.filter(pk=int(approval.case_id)).first()
        tenant_id = case.tenant_id if case else "default"
        persist_runtime_outbox_event(
            event_id=f"approval:{approval.approval_id}:{event_suffix}",
            case=case,
            event_type=f"approval.{event_suffix}",
            source="approval_gateway",
            tenant_id=tenant_id,
            correlation_id=approval.correlation_id,
            trace_id=approval.correlation_id,
            payload=approval.to_dict(),
            causation_id=approval.approval_id,
        )

    @classmethod
    async def _emit_approval_requested_event(cls, approval: ApprovalRequest):
        await cls._emit_runtime_event(approval, "requested")

    @classmethod
    async def _emit_approval_granted_event(cls, approval: ApprovalRequest):
        await cls._emit_runtime_event(approval, "granted")

    @classmethod
    async def _emit_approval_rejected_event(cls, approval: ApprovalRequest):
        await cls._emit_runtime_event(approval, "rejected")

    @classmethod
    async def _emit_approval_changes_requested_event(cls, approval: ApprovalRequest):
        await cls._emit_runtime_event(approval, "changes_requested")

    @classmethod
    async def _emit_approval_escalated_event(cls, approval: ApprovalRequest):
        await cls._emit_runtime_event(approval, "escalated")

    @classmethod
    async def _emit_approval_expired_event(cls, approval: ApprovalRequest):
        await cls._emit_runtime_event(approval, "expired")


def initialize_default_approval_policies():
    """Inicializa políticas padrão de aprovação."""

    proposal_policy = ApprovalPolicy(
        requires_approval=True,
        approval_fields=["discount", "custom_terms", "total_value"],
        approvers=["sales_manager@company.com", "cfo@company.com"],
        deadline_minutes=120,
        escalation_deadline_minutes=60,
        priority=ApprovalPriority.URGENT,
    )
    ApprovalGateway.register_policy("proposal.send", proposal_policy)

    discount_policy = ApprovalPolicy(
        requires_approval=True,
        approval_fields=["discount_percent", "justification"],
        approvers=["sales_manager@company.com"],
        deadline_minutes=60,
        escalation_deadline_minutes=30,
        priority=ApprovalPriority.URGENT,
    )
    ApprovalGateway.register_policy("apply.discount", discount_policy)

    refund_policy = ApprovalPolicy(
        requires_approval=True,
        approval_fields=["refund_amount", "reason"],
        approvers=["finance_manager@company.com", "cfo@company.com"],
        deadline_minutes=240,
        escalation_deadline_minutes=180,
        priority=ApprovalPriority.URGENT,
    )
    ApprovalGateway.register_policy("process.refund", refund_policy)

    cancellation_policy = ApprovalPolicy(
        requires_approval=True,
        approval_fields=["reason", "early_termination_penalty"],
        approvers=["sales_director@company.com", "cfo@company.com"],
        deadline_minutes=360,
        escalation_deadline_minutes=180,
        priority=ApprovalPriority.ROUTINE,
    )
    ApprovalGateway.register_policy("cancel.contract", cancellation_policy)


initialize_default_approval_policies()
