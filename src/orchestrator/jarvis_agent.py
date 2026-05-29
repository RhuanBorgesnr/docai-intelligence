"""
Jarvis Agent — the executive orchestrator.

Jarvis is the central brain that:
1. Receives events or periodic triggers
2. Evaluates the current case state
3. Decides which specialist to invoke (routing)
4. Dispatches work via the inter-agent bus
5. Monitors progress and handles escalations
6. Generates executive briefings

The routing logic is rule-based (deterministic) for reliability,
with optional LLM-assisted reasoning for complex cases.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# ── Routing rules ─────────────────────────────────────────────────────────────
# Maps case state → (target_agent, default_instruction)

ROUTING_TABLE: dict[str, tuple[str, str]] = {
    "new":                    ("intake",  "Classificar e triar este novo lead"),
    "triage":                 ("intake",  "Validar dados e preparar qualificação"),
    "qualified":              ("sdr",     "Qualificar oportunidade e coletar requisitos"),
    "waiting_doc_sample":     ("sdr",     "Solicitar documentos ao cliente"),
    "doc_sent_to_docai":      ("docai",   "Processar e analisar documentos recebidos"),
    "analysis_ready":         ("sales",   "Preparar proposta com base na análise"),
    "proposal_draft_ready":   ("sales",   "Revisar proposta e solicitar aprovação"),
    "approved_to_send":       ("sales",   "Enviar proposta aprovada ao cliente"),
    "followup_scheduled":     ("sdr",     "Executar follow-up agendado"),
}

# States where no agent action is needed (terminal / waiting external input)
TERMINAL_STATES = {"won", "lost", "closed", "failed", "blocked"}
WAITING_STATES = {"waiting_human_approval"}


@dataclass
class JarvisDecision:
    """Result of Jarvis evaluating a case."""

    case_id: int
    action: str  # "route", "wait", "escalate", "skip"
    target_agent: str | None = None
    instruction: str = ""
    reason: str = ""


class JarvisAgent:
    """
    Executive orchestrator that decides what happens next for a case.

    Usage::

        jarvis = JarvisAgent()
        decision = jarvis.evaluate_case(case_id)
        if decision.action == "route":
            jarvis.dispatch(decision)
    """

    def evaluate_case(self, case_id: int) -> JarvisDecision:
        """
        Deterministic routing: look at case state and decide next action.
        """
        from orchestrator.models import Case

        try:
            case = Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            return JarvisDecision(case_id=case_id, action="skip", reason="Case not found")

        if case.state in TERMINAL_STATES:
            return JarvisDecision(
                case_id=case_id,
                action="skip",
                reason=f"Case in terminal state: {case.state}",
            )

        if case.state in WAITING_STATES:
            # Check if approval is overdue → escalate
            from approvals.models import Approval

            overdue = Approval.objects.filter(
                case=case, status="pending", deadline_at__lt=timezone.now(),
            ).exists()

            if overdue:
                return JarvisDecision(
                    case_id=case_id,
                    action="escalate",
                    reason="Approval overdue — needs human intervention",
                )
            return JarvisDecision(
                case_id=case_id,
                action="wait",
                reason=f"Waiting for human approval",
            )

        route = ROUTING_TABLE.get(case.state)
        if not route:
            return JarvisDecision(
                case_id=case_id,
                action="skip",
                reason=f"No routing rule for state: {case.state}",
            )

        target_agent, instruction = route
        return JarvisDecision(
            case_id=case_id,
            action="route",
            target_agent=target_agent,
            instruction=instruction,
            reason=f"State {case.state} routes to {target_agent}",
        )

    def dispatch(self, decision: JarvisDecision) -> dict:
        """
        Execute a routing decision by sending a command via the tools layer.
        """
        from orchestrator.jarvis_tools import route_to_agent, send_notification

        if decision.action == "route" and decision.target_agent:
            return route_to_agent(
                case_id=decision.case_id,
                target_agent=decision.target_agent,
                instruction=decision.instruction,
            )

        if decision.action == "escalate":
            return send_notification(
                case_id=decision.case_id,
                channel="email",
                recipient="manager@company.com",
                subject="[ESCALATION] Aprovação vencida",
                message=f"Case {decision.case_id}: {decision.reason}",
            )

        return {"action": decision.action, "reason": decision.reason}

    def process_event(self, case_id: int) -> dict:
        """
        Full evaluate → dispatch cycle.  Called by workflow hooks.
        """
        decision = self.evaluate_case(case_id)
        logger.info(
            "[jarvis] case=%s action=%s target=%s reason=%s",
            case_id,
            decision.action,
            decision.target_agent,
            decision.reason,
        )

        if decision.action in ("route", "escalate"):
            result = self.dispatch(decision)
            return {"decision": decision.__dict__, "dispatch": result}

        return {"decision": decision.__dict__}

    # ── Briefing ──────────────────────────────────────────────────────────────

    def generate_briefing(self, tenant_id: Optional[str] = None) -> dict:
        """
        Build a structured executive briefing from current metrics.

        Can optionally be enhanced by LLM summarisation.
        """
        from orchestrator.jarvis_tools import list_pending_approvals, view_metrics

        metrics = view_metrics(tenant_id=tenant_id)
        approvals = list_pending_approvals(tenant_id=tenant_id)

        # Identify anomalies / action items
        alerts: list[str] = []

        pipeline = metrics.get("pipeline", {})
        if pipeline.get("failed", 0) > 0:
            alerts.append(f"{pipeline['failed']} case(s) em estado FAILED — investigar")

        health = metrics.get("health", {})
        if health.get("dlq_size", 0) > 0:
            alerts.append(f"{health['dlq_size']} evento(s) na dead-letter queue")

        for cb in health.get("circuit_breakers", []):
            if cb.get("is_open"):
                alerts.append(f"Circuit breaker ABERTO para canal {cb['channel']}")

        overdue_apvs = [a for a in approvals.get("approvals", []) if a.get("overdue")]
        if overdue_apvs:
            alerts.append(f"{len(overdue_apvs)} aprovação(ões) vencida(s)")

        notif = metrics.get("notifications", {})
        if notif.get("failed", 0) > 0:
            alerts.append(f"{notif['failed']} notificação(ões) falharam")

        throughput = metrics.get("throughput", {})

        briefing = {
            "generated_at": timezone.now().isoformat(),
            "tenant_id": tenant_id,
            "summary": {
                "active_cases": pipeline.get("active", 0),
                "completed_30d": throughput.get("completed", 0),
                "created_30d": throughput.get("created", 0),
                "avg_resolution_hours": throughput.get("avg_resolution_hours"),
                "pending_approvals": approvals.get("count", 0),
                "overdue_approvals": len(overdue_apvs),
                "pending_notifications": notif.get("pending", 0),
            },
            "alerts": alerts,
            "alert_count": len(alerts),
            "pipeline_breakdown": pipeline.get("by_state", {}),
        }

        # Sprint 4 / B3 — overlay commercial executive signals.
        try:
            from orchestrator.executive_signals import build_executive_overlay

            overlay = build_executive_overlay(tenant_id=tenant_id)
            briefing["commercial"] = overlay["commercial"]
            briefing["top_priorities"] = overlay["top_priorities"]
            briefing["alerts"] = list(briefing["alerts"]) + overlay["alerts"]
            briefing["alert_count"] = len(briefing["alerts"])
        except Exception as exc:  # noqa: BLE001 - overlay must never break the briefing
            logger.warning("Executive overlay unavailable: %s", exc)

        return briefing
