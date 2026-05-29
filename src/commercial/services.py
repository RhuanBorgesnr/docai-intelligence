"""
Commercial services.

Public entry points:

- ``ingest_lead``           — capture a lead, create Case, emit ``lead.received``,
                              run pre-score, queue SDR qualification.
- ``recompute_score``       — recalculate score and persist a ``LeadScoreEvent``.
- ``qualify_lead``          — invoke the SDR Agent and update the lead.
- ``create_opportunity``    — promote a qualified lead into the pipeline.
- ``transition_opportunity``— move opportunity stage with audit + event.
- ``draft_followup``        — generate a follow-up draft via Sales Agent and
                              register the required approval.

All operations are scoped to the ``docai_internal`` tenant by default and reuse
the Sprint 1–3 infrastructure (orchestrator events, audit, approvals).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from agent_runtime.prompt_registry import AgentType
from agent_runtime.runner import AgentExecutionResult, AgentRunner
from approvals.gateway import ApprovalGateway
from audit.services import write_audit_log
from commercial.enums import (
    ACTIVE_OPPORTUNITY_STAGES,
    LeadSource,
    LeadStatus,
    OpportunityStage,
)
from commercial.models import FollowUpDraft, Lead, LeadScoreEvent, Opportunity
from commercial.scoring import ScoreBreakdown, compute_lead_score
from core.governance import (
    DecisionLineage,
    record_external_action,
    requires_approval,
)
from core.tenants import INTERNAL_TENANT_ID, resolve_tenant_id
from orchestrator.enums import EventType, Priority
from orchestrator.services import ingest_event

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _new_correlation_id() -> str:
    return f"corr_{uuid.uuid4().hex[:16]}"


def _new_event_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _hash_inputs(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _run_async(coro):
    """Run an async coroutine from sync code (Celery-safe)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Inside an existing loop: run in a new event loop in current thread.
            return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=120)
    except RuntimeError:
        pass
    return asyncio.run(coro)


# ── Lead ingestion ───────────────────────────────────────────────────────────

@dataclass
class LeadIngestionResult:
    lead: Lead
    created: bool
    score: ScoreBreakdown


def ingest_lead(
    *,
    source: str,
    contact_name: str = "",
    contact_email: str = "",
    contact_phone: str = "",
    company_name: str = "",
    industry: str = "",
    company_size: str = "",
    country: str = "BR",
    payload: dict[str, Any] | None = None,
    consent_given: bool = False,
    tenant_id: str | None = None,
    correlation_id: str | None = None,
    external_lead_id: str | None = None,
) -> LeadIngestionResult:
    """
    Capture a new commercial lead.

    - Idempotent on (tenant_id, contact_email) when an email is provided.
    - Always runs deterministic pre-scoring.
    - Creates an orchestrator Case via ``lead.received`` so the existing
      workflow engine, audit and memory snapshots kick in.
    """
    tenant = resolve_tenant_id(tenant_id, default=INTERNAL_TENANT_ID)
    correlation_id = correlation_id or _new_correlation_id()
    payload = payload or {}

    # Idempotency: by external id if given, else by (tenant, email).
    existing: Lead | None = None
    if external_lead_id:
        existing = Lead.objects.filter(lead_id=external_lead_id).first()
    elif contact_email:
        existing = Lead.objects.filter(
            tenant_id=tenant, contact_email__iexact=contact_email
        ).first()

    score = compute_lead_score(
        source=source,
        industry=industry,
        company_size=company_size,
        country=country,
        contact_email=contact_email,
        company_name=company_name,
        consent_given=consent_given,
        payload=payload,
    )

    with transaction.atomic():
        if existing:
            lead = existing
            lead.last_event_at = timezone.now()
            # Update score if it improved (don't downgrade silently).
            if score.total > lead.score:
                _persist_score_change(lead, lead.score, score, reason="reingest_pre_score")
                lead.score = score.total
                lead.icp_fit = score.icp_fit
            lead.save(update_fields=["last_event_at", "score", "icp_fit", "updated_at"])
            created = False
        else:
            lead = Lead.objects.create(
                tenant_id=tenant,
                source=source if source in LeadSource.values else LeadSource.OTHER,
                status=LeadStatus.NEW,
                score=score.total,
                contact_name=contact_name,
                contact_email=contact_email,
                contact_phone=contact_phone,
                company_name=company_name,
                industry=industry,
                company_size=company_size,
                country=country,
                payload=payload,
                icp_fit=score.icp_fit,
                consent_given=consent_given,
                correlation_id=correlation_id,
                lead_id=external_lead_id or _new_event_id("lead"),
            )
            LeadScoreEvent.objects.create(
                lead=lead,
                score_before=0,
                score_after=score.total,
                reason="initial_pre_score",
                details=score.to_dict(),
            )
            created = True

        # Emit lead.received event into the orchestrator so a Case is created.
        event_payload = {
            "case_id": lead.lead_id,  # use lead_id as external_ref
            "title": f"Lead {lead.company_name or lead.contact_email or lead.lead_id}",
            "lead_id": lead.lead_id,
            "source": lead.source,
            "company_name": lead.company_name,
            "contact_email": lead.contact_email,
            "industry": lead.industry,
            "score": lead.score,
            "icp_fit": lead.icp_fit,
        }
        ingestion = ingest_event(
            data={
                "event_id": _new_event_id("evt_lead_recv"),
                "event_type": EventType.LEAD_RECEIVED,
                "source": f"commercial.ingest.{source}",
                "occurred_at": timezone.now(),
                "correlation_id": correlation_id,
                "tenant_id": tenant,
                "priority": Priority.MEDIUM if lead.score < 70 else Priority.HIGH,
                "payload": event_payload,
                "meta": {"trace_id": correlation_id},
            }
        )
        if lead.case_id is None:
            lead.case = ingestion.event.case
            lead.save(update_fields=["case", "updated_at"])

        write_audit_log(
            action="commercial.lead.ingested" if created else "commercial.lead.reingested",
            case_id=lead.case_id,
            actor_type="system",
            actor_id="commercial.ingest",
            trace_id=correlation_id,
            correlation_id=correlation_id,
            details={
                "lead_id": lead.lead_id,
                "tenant_id": tenant,
                "source": source,
                "score": lead.score,
                "icp_fit": lead.icp_fit,
                "consent_given": consent_given,
            },
        )

    # Best-effort: queue SDR qualification asynchronously.
    try:
        from commercial.tasks import qualify_lead_task

        qualify_lead_task.delay(lead.id)
    except Exception:
        # Sync fallback for local dev / no broker — don't crash ingestion.
        logger.info("Falling back to synchronous SDR qualification for lead %s", lead.lead_id)
        try:
            qualify_lead(lead.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sync SDR qualification failed for %s: %s", lead.lead_id, exc)

    return LeadIngestionResult(lead=lead, created=created, score=score)


# ── Scoring ──────────────────────────────────────────────────────────────────

def _persist_score_change(
    lead: Lead, before: int, score: ScoreBreakdown, *, reason: str
) -> None:
    LeadScoreEvent.objects.create(
        lead=lead,
        score_before=before,
        score_after=score.total,
        reason=reason,
        details=score.to_dict(),
    )


def recompute_score(lead: Lead, *, reason: str = "manual_recompute") -> ScoreBreakdown:
    score = compute_lead_score(
        source=lead.source,
        industry=lead.industry,
        company_size=lead.company_size,
        country=lead.country,
        contact_email=lead.contact_email,
        company_name=lead.company_name,
        consent_given=lead.consent_given,
        payload=lead.payload or {},
    )
    if score.total != lead.score:
        before = lead.score
        with transaction.atomic():
            lead.score = score.total
            lead.icp_fit = score.icp_fit
            lead.save(update_fields=["score", "icp_fit", "updated_at"])
            _persist_score_change(lead, before, score, reason=reason)
    return score


# ── SDR qualification ────────────────────────────────────────────────────────

@dataclass
class QualificationOutcome:
    lead: Lead
    qualified: bool
    confidence: float
    reason: str
    opportunity: Opportunity | None
    agent_result: AgentExecutionResult | None


def qualify_lead(lead_id: int) -> QualificationOutcome:
    """
    Run the SDR Agent against ``lead`` and update its status / score.

    Reuses ``agent_runtime`` so prompt versioning, retries, cache and metrics
    are inherited from Sprint 2.
    """
    lead = Lead.objects.select_related("case").get(pk=lead_id)
    if lead.status == LeadStatus.QUALIFYING:
        logger.debug("Lead %s already in QUALIFYING; skipping duplicate run", lead.lead_id)
    lead.status = LeadStatus.QUALIFYING
    lead.save(update_fields=["status", "updated_at"])

    correlation_id = lead.correlation_id or _new_correlation_id()

    context = {
        "lead_profile": {
            "lead_id": lead.lead_id,
            "company_name": lead.company_name,
            "contact_email": lead.contact_email,
            "industry": lead.industry,
            "company_size": lead.company_size,
            "country": lead.country,
            "source": lead.source,
            "pre_score": lead.score,
            "icp_fit": lead.icp_fit,
            "payload": lead.payload,
        },
        "interaction_history": [],
    }

    from core.settings import LLM_PROVIDER
    runner = AgentRunner(llm_provider=LLM_PROVIDER)
    result = _run_async(
        runner.execute_agent_command(
            agent_type=AgentType.SDR,
            context=context,
            correlation_id=correlation_id,
            use_cache=False,
        )
    )

    output = result.output or {}
    qualified = bool(output.get("qualified", lead.score >= 60))
    confidence = float(output.get("confidence", 0.0) or 0.0)
    reason = (
        output.get("next_action")
        or output.get("reason")
        or ("ICP heuristic" if lead.score >= 60 else "Below ICP threshold")
    )

    # Lineage for B7.
    lineage = DecisionLineage(
        agent_type=AgentType.SDR.value,
        decision="qualified" if qualified else "disqualified",
        prompt_version=1,
        model_name=getattr(result.metrics, "to_dict", lambda: {})().get("model", ""),
        provider="openai",
        inputs_hash=_hash_inputs(context),
        confidence=confidence,
        extra={"raw_output_keys": list(output.keys())},
    )

    opportunity: Opportunity | None = None
    with transaction.atomic():
        lead.qualification_reason = reason
        lead.status = LeadStatus.QUALIFIED if qualified else LeadStatus.DISQUALIFIED
        # Boost score if agent confidence is high and disagrees with heuristic.
        if qualified and confidence >= 0.7 and lead.score < 70:
            before = lead.score
            lead.score = max(lead.score, 70)
            LeadScoreEvent.objects.create(
                lead=lead,
                score_before=before,
                score_after=lead.score,
                reason="sdr_agent_boost",
                details={"confidence": confidence},
            )
        lead.save(update_fields=["status", "qualification_reason", "score", "updated_at"])

        # Audit + lineage in append-only trail.
        write_audit_log(
            action=("commercial.lead.qualified" if qualified else "commercial.lead.disqualified"),
            case_id=lead.case_id,
            actor_type="agent",
            actor_id=AgentType.SDR.value,
            trace_id=correlation_id,
            correlation_id=correlation_id,
            details={
                "lead_id": lead.lead_id,
                "confidence": confidence,
                "reason": reason,
                "lineage": lineage.to_dict(),
            },
        )

        # Emit downstream event.
        event_type = EventType.LEAD_QUALIFIED if qualified else EventType.LEAD_DISQUALIFIED
        ingest_event(
            data={
                "event_id": _new_event_id("evt_lead_q"),
                "event_type": event_type,
                "source": f"commercial.sdr_agent",
                "occurred_at": timezone.now(),
                "correlation_id": correlation_id,
                "tenant_id": lead.tenant_id,
                "priority": Priority.HIGH if qualified else Priority.LOW,
                "payload": {
                    "case_id": lead.lead_id,
                    "lead_id": lead.lead_id,
                    "qualified": qualified,
                    "confidence": confidence,
                    "reason": reason,
                },
                "meta": {"trace_id": correlation_id, "lineage": lineage.to_dict()},
            }
        )

        if qualified:
            opportunity = create_opportunity(lead, correlation_id=correlation_id)

    return QualificationOutcome(
        lead=lead,
        qualified=qualified,
        confidence=confidence,
        reason=reason,
        opportunity=opportunity,
        agent_result=result,
    )


# ── Opportunity lifecycle ────────────────────────────────────────────────────

def create_opportunity(
    lead: Lead, *, correlation_id: str | None = None, estimated_value: float = 0.0
) -> Opportunity:
    correlation_id = correlation_id or lead.correlation_id or _new_correlation_id()
    with transaction.atomic():
        opp = Opportunity.objects.create(
            tenant_id=lead.tenant_id,
            lead=lead,
            case=lead.case,
            stage=OpportunityStage.QUALIFIED,
            estimated_value=estimated_value,
            win_probability=0.3,
        )
        lead.status = LeadStatus.CONVERTED
        lead.save(update_fields=["status", "updated_at"])

        write_audit_log(
            action="commercial.opportunity.created",
            case_id=lead.case_id,
            actor_type="agent",
            actor_id=AgentType.SDR.value,
            trace_id=correlation_id,
            correlation_id=correlation_id,
            details={"opportunity_id": opp.opportunity_id, "lead_id": lead.lead_id},
        )

        ingest_event(
            data={
                "event_id": _new_event_id("evt_opp_new"),
                "event_type": EventType.OPPORTUNITY_CREATED,
                "source": "commercial.sdr_agent",
                "occurred_at": timezone.now(),
                "correlation_id": correlation_id,
                "tenant_id": lead.tenant_id,
                "priority": Priority.HIGH,
                "payload": {
                    "case_id": lead.lead_id,
                    "opportunity_id": opp.opportunity_id,
                    "lead_id": lead.lead_id,
                    "stage": opp.stage,
                },
                "meta": {"trace_id": correlation_id},
            }
        )
    return opp


def transition_opportunity(
    opp: Opportunity, *, new_stage: str, actor_id: str = "system", reason: str = ""
) -> Opportunity:
    if new_stage not in OpportunityStage.values:
        raise ValueError(f"Invalid stage: {new_stage}")
    previous = opp.stage
    correlation_id = _new_correlation_id()
    with transaction.atomic():
        opp.stage = new_stage
        if new_stage in (OpportunityStage.WON, OpportunityStage.LOST):
            opp.closed_at = timezone.now()
        opp.save()
        write_audit_log(
            action="commercial.opportunity.stage_changed",
            case_id=opp.case_id,
            actor_type="user" if actor_id != "system" else "system",
            actor_id=actor_id,
            trace_id=correlation_id,
            correlation_id=correlation_id,
            details={
                "opportunity_id": opp.opportunity_id,
                "previous_stage": previous,
                "new_stage": new_stage,
                "reason": reason,
            },
        )
        ingest_event(
            data={
                "event_id": _new_event_id("evt_opp_stage"),
                "event_type": EventType.OPPORTUNITY_STAGE_CHANGED,
                "source": "commercial.api",
                "occurred_at": timezone.now(),
                "correlation_id": correlation_id,
                "tenant_id": opp.tenant_id,
                "payload": {
                    "case_id": opp.lead.lead_id,
                    "opportunity_id": opp.opportunity_id,
                    "previous_stage": previous,
                    "new_stage": new_stage,
                },
                "meta": {"trace_id": correlation_id},
            }
        )
    return opp


# ── Follow-up draft (approval-first) ─────────────────────────────────────────

def draft_followup(
    lead: Lead,
    *,
    channel: str = FollowUpDraft.Channel.EMAIL,
    extra_context: dict[str, Any] | None = None,
) -> FollowUpDraft:
    """
    Generate a follow-up draft via Sales Agent and request human approval.

    Approval-first: the draft is persisted in PENDING_APPROVAL state and an
    Approval row is created via ``approvals.gateway``. The notification is
    only dispatched after the approval is granted (handled elsewhere).
    """
    correlation_id = lead.correlation_id or _new_correlation_id()
    extra_context = extra_context or {}

    context = {
        "opportunity": {
            "lead_id": lead.lead_id,
            "company_name": lead.company_name,
            "contact_email": lead.contact_email,
            "industry": lead.industry,
            "score": lead.score,
            "icp_fit": lead.icp_fit,
            "qualification_reason": lead.qualification_reason,
        },
        "docai_analysis": extra_context.get("docai_analysis", {}),
        "negotiation_history": extra_context.get("history", []),
    }

    from core.settings import LLM_PROVIDER
    runner = AgentRunner(llm_provider=LLM_PROVIDER)
    result = _run_async(
        runner.execute_agent_command(
            agent_type=AgentType.SALES,
            context=context,
            correlation_id=correlation_id,
            use_cache=False,
        )
    )
    output = result.output or {}

    proposal = output.get("proposal") or {}
    subject = (
        proposal.get("subject")
        or f"Próximos passos com a DocAI — {lead.company_name or 'sua empresa'}"
    )
    body = (
        proposal.get("body")
        or proposal.get("message")
        or "Olá,\n\nObrigado pelo seu interesse na DocAI. Gostaríamos de agendar "
           "uma demonstração personalizada com base no seu perfil.\n\nAtenciosamente,\nEquipe DocAI"
    )

    lineage = DecisionLineage(
        agent_type=AgentType.SALES.value,
        decision="followup_drafted",
        prompt_version=1,
        provider="openai",
        inputs_hash=_hash_inputs(context),
        confidence=float(output.get("win_probability", 0.0) or 0.0),
    )

    with transaction.atomic():
        draft = FollowUpDraft.objects.create(
            tenant_id=lead.tenant_id,
            lead=lead,
            channel=channel,
            subject=subject,
            body=body,
            status=FollowUpDraft.Status.PENDING_APPROVAL,
            created_by_agent=AgentType.SALES.value,
            correlation_id=correlation_id,
            lineage=lineage.to_dict(),
        )

        # Request approval (approval-first governance).
        action = "commercial.followup.send"
        if requires_approval(action) and lead.case_id:
            approval_id = f"appr_{uuid.uuid4().hex[:16]}"
            try:
                _run_async(
                    ApprovalGateway.request_approval(
                        approval_id=approval_id,
                        case_id=str(lead.case_id),
                        correlation_id=correlation_id,
                        agent_type=AgentType.SALES.value,
                        action=action,
                        data_to_approve={
                            "channel": channel,
                            "subject": subject,
                            "body": body,
                            "recipient": lead.contact_email or lead.contact_phone,
                        },
                        affected_fields=["subject", "body", "recipient"],
                        context={"lead_id": lead.lead_id},
                    )
                )
                draft.approval_id = approval_id
                draft.save(update_fields=["approval_id", "updated_at"])
            except Exception as exc:  # noqa: BLE001
                logger.warning("Approval gateway unavailable, draft kept pending: %s", exc)

        # Lineage + audit.
        record_external_action(
            action=action,
            actor_type="agent",
            actor_id=AgentType.SALES.value,
            case_id=lead.case_id,
            correlation_id=correlation_id,
            trace_id=correlation_id,
            tenant_id=lead.tenant_id,
            target=lead.contact_email or lead.contact_phone or lead.lead_id,
            payload_summary={"channel": channel, "subject": subject},
            lineage=lineage,
            approval_id=draft.approval_id,
        )

        # Emit followup.drafted event.
        ingest_event(
            data={
                "event_id": _new_event_id("evt_fup_draft"),
                "event_type": EventType.FOLLOWUP_DRAFTED,
                "source": "commercial.sales_agent",
                "occurred_at": timezone.now(),
                "correlation_id": correlation_id,
                "tenant_id": lead.tenant_id,
                "payload": {
                    "case_id": lead.lead_id,
                    "lead_id": lead.lead_id,
                    "draft_id": draft.draft_id,
                    "channel": channel,
                    "approval_id": draft.approval_id,
                },
                "meta": {"trace_id": correlation_id},
            }
        )

    return draft
