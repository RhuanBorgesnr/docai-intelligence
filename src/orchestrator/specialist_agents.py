"""
Specialist Agents — lightweight wrappers that execute LLM prompts via
AgentRunner for specific business functions.

Each agent:
1. Receives a case context (via ``process_case``)
2. Builds a contextualised user message
3. Calls AgentRunner with the registered prompt + policy
4. Returns a structured result

The agents don't make state transitions themselves — they return
``recommended_action`` to Jarvis who decides what to do next.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from agent_runtime.prompt_registry import AgentType
from agent_runtime.runner import AgentExecutionResult, AgentRunner

logger = logging.getLogger(__name__)


@dataclass
class AgentCaseContext:
    """Minimal context passed to a specialist agent."""

    case_id: int
    external_ref: str
    title: str
    state: str
    priority: str
    instruction: str = ""
    rag_context: str = ""
    metadata: dict | None = None


def _build_user_message(ctx: AgentCaseContext, role_hint: str) -> str:
    """Assemble the user-message string sent to the LLM."""
    parts = [
        f"Case: {ctx.title} (ref: {ctx.external_ref})",
        f"Estado atual: {ctx.state}",
        f"Prioridade: {ctx.priority}",
    ]
    if ctx.instruction:
        parts.append(f"Instrução do Jarvis: {ctx.instruction}")
    if ctx.rag_context:
        parts.append(f"\n--- Contexto RAG ---\n{ctx.rag_context[:2000]}")
    if ctx.metadata:
        parts.append(f"Metadata: {str(ctx.metadata)[:500]}")
    parts.append(f"\nVocê é o {role_hint}. Analise e retorne JSON com sua recomendação.")
    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
#  Specialist classes
# ══════════════════════════════════════════════════════════════════════════════

class _BaseSpecialist:
    """Shared execution logic for all specialists."""

    agent_type: AgentType
    role_hint: str = "Agente"

    def __init__(self, runner: Optional[AgentRunner] = None):
        self.runner = runner or AgentRunner()

    async def process_case(self, ctx: AgentCaseContext) -> AgentExecutionResult:
        """Execute the specialist prompt for the given case context."""
        user_message = _build_user_message(ctx, self.role_hint)
        result = await self.runner.execute(
            agent_type=self.agent_type,
            user_message=user_message,
        )
        logger.info(
            "[%s] case=%s status=%s",
            self.agent_type.value,
            ctx.external_ref,
            result.status.value,
        )
        return result


class IntakeAgent(_BaseSpecialist):
    """Receives new leads, validates and classifies them."""

    agent_type = AgentType.INTAKE
    role_hint = "Intake Agent — recepção e triagem de leads"


class SDRAgent(_BaseSpecialist):
    """Qualifies leads and gathers preliminary info."""

    agent_type = AgentType.SDR
    role_hint = "SDR Agent — qualificação de oportunidades"


class SalesAgent(_BaseSpecialist):
    """Generates proposals, negotiates, closes deals."""

    agent_type = AgentType.SALES
    role_hint = "Sales Agent — propostas e negociação"


class DocAIOperatorAgent(_BaseSpecialist):
    """Coordinates document analysis with the DocAI subsystem."""

    agent_type = AgentType.DOCAI_OPERATOR
    role_hint = "DocAI Operator — análise inteligente de documentos"


class AnalystAgent(_BaseSpecialist):
    """Performs data analysis and generates insights."""

    agent_type = AgentType.ANALYST
    role_hint = "Analyst Agent — análise de dados e indicadores"


# ── Registry (maps agent id → class) ─────────────────────────────────────────

SPECIALIST_REGISTRY: dict[str, type[_BaseSpecialist]] = {
    "intake": IntakeAgent,
    "sdr": SDRAgent,
    "sales": SalesAgent,
    "docai": DocAIOperatorAgent,
    "analyst": AnalystAgent,
}


def get_specialist(agent_id: str) -> _BaseSpecialist:
    """Instantiate a specialist by its dashboard id."""
    cls = SPECIALIST_REGISTRY.get(agent_id)
    if not cls:
        raise ValueError(f"Unknown specialist: {agent_id}")
    return cls()
