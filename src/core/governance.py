"""
Governance helpers for Sprint 4 (B7).

Centralises three governance concerns that every Sprint 4 agent / workflow
must apply when acting on the world:

1. **Approval policies** — canonical catalogue of which actions require human
   approval before being executed.
2. **Audit trail** — convenience wrapper around ``audit.services.write_audit_log``
   for "external action" entries.
3. **Decision lineage** — structured details captured for every agent decision
   so we can answer *why did the agent do X?* later.

This module intentionally has **no Django model**. All structured data is
persisted via ``audit.AuditLog.details`` JSON, keeping the change additive and
fully reusing Sprint 1 infrastructure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from audit.services import write_audit_log


# ── Approval policy catalogue ────────────────────────────────────────────────

@dataclass(frozen=True)
class ApprovalPolicySpec:
    """Declarative approval policy for a sensitive action."""
    action: str
    required: bool
    approver_roles: tuple[str, ...] = ("ops", "executive")
    sla_minutes: int = 60
    description: str = ""


# Canonical Sprint 4 catalogue. Add to this list — never remove without
# documenting a migration path.
SPRINT4_APPROVAL_POLICIES: tuple[ApprovalPolicySpec, ...] = (
    ApprovalPolicySpec(
        action="commercial.followup.send",
        required=True,
        sla_minutes=30,
        description="Send a follow-up message (email/WhatsApp) to a lead.",
    ),
    ApprovalPolicySpec(
        action="commercial.proposal.send",
        required=True,
        approver_roles=("ops", "executive"),
        sla_minutes=120,
        description="Send a commercial proposal to a lead.",
    ),
    ApprovalPolicySpec(
        action="commercial.lead.disqualify",
        required=False,
        sla_minutes=0,
        description="Mark a lead as disqualified by SDR Agent.",
    ),
    ApprovalPolicySpec(
        action="docai.demo.run",
        required=False,
        sla_minutes=0,
        description="Run an automated DocAI demo on a lead's document.",
    ),
    ApprovalPolicySpec(
        action="executive.alert.broadcast",
        required=False,
        sla_minutes=0,
        description="Broadcast an executive alert to internal channels.",
    ),
)

_POLICIES_BY_ACTION: dict[str, ApprovalPolicySpec] = {
    p.action: p for p in SPRINT4_APPROVAL_POLICIES
}


def get_approval_policy(action: str) -> ApprovalPolicySpec | None:
    """Return the policy registered for ``action`` (or ``None``)."""
    return _POLICIES_BY_ACTION.get(action)


def requires_approval(action: str) -> bool:
    """True if ``action`` requires human approval before being executed."""
    policy = _POLICIES_BY_ACTION.get(action)
    return bool(policy and policy.required)


# ── Decision lineage ─────────────────────────────────────────────────────────

@dataclass
class DecisionLineage:
    """
    Captures the *why* behind an agent decision.

    Persisted inside ``AuditLog.details`` so it lives in the same append-only
    table as every other audit event (no schema migration needed).
    """
    agent_type: str
    decision: str
    prompt_version: int | None = None
    model_name: str = ""
    provider: str = ""
    inputs_hash: str = ""
    retrieved_context_ids: list[str] = field(default_factory=list)
    confidence: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "decision": self.decision,
            "prompt_version": self.prompt_version,
            "model_name": self.model_name,
            "provider": self.provider,
            "inputs_hash": self.inputs_hash,
            "retrieved_context_ids": list(self.retrieved_context_ids),
            "confidence": self.confidence,
            **({"extra": self.extra} if self.extra else {}),
        }


# ── External-action audit helper ─────────────────────────────────────────────

def record_external_action(
    *,
    action: str,
    actor_type: str,
    actor_id: str,
    case_id: int | None = None,
    correlation_id: str = "",
    trace_id: str = "",
    tenant_id: str = "",
    target: str = "",
    payload_summary: dict[str, Any] | None = None,
    lineage: DecisionLineage | None = None,
    approval_id: str = "",
) -> None:
    """
    Record an action that affects the outside world (or another tenant) into
    the audit trail with full Sprint 4 governance metadata.

    Always call this **after** the action succeeds (or fails — pass status in
    ``payload_summary``). Approval requirement is checked separately by the
    caller via :func:`requires_approval`.
    """
    details: dict[str, Any] = {
        "action": action,
        "tenant_id": tenant_id,
        "target": target,
        "approval_id": approval_id,
        "policy_required_approval": requires_approval(action),
    }
    if payload_summary:
        details["payload_summary"] = payload_summary
    if lineage:
        details["lineage"] = lineage.to_dict()

    write_audit_log(
        action=f"external.{action}",
        case_id=case_id,
        actor_type=actor_type,
        actor_id=actor_id,
        trace_id=trace_id,
        correlation_id=correlation_id,
        details=details,
    )


__all__ = [
    "ApprovalPolicySpec",
    "DecisionLineage",
    "SPRINT4_APPROVAL_POLICIES",
    "get_approval_policy",
    "requires_approval",
    "record_external_action",
]
