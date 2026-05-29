"""
Agent Charter Registry — the organizational chart of the digital team.

Each agent in the Theo/OpenClaw platform is defined not as an isolated
automation, but as a **team member** with:

- Role & title (what they do)
- Operational responsibility (what they own)
- Routine schedule (when they work proactively)
- Deliverables (what they produce)
- KPIs / metrics (how they're measured)
- Autonomy limits (what they can do alone)
- Approval gates (what requires human sign-off)
- Communication channels (who they talk to)
- Business impact (how they affect revenue)

Vision:
    DocAI   = the product we sell
    Theo/OpenClaw = the digital company that operates, sells and supports DocAI

Sprint 4 / Phase 3.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent_runtime.prompt_registry import AgentType


# ── Agent Status ──────────────────────────────────────────────────────────────

class AgentStatus(str, Enum):
    """Operational status of a team member."""
    ACTIVE = "active"          # Fully operational
    STANDBY = "standby"        # Ready but not running routines
    DEGRADED = "degraded"      # Partially operational (e.g. LLM down, using fallbacks)
    DISABLED = "disabled"      # Manually paused by ops


class RoutineFrequency(str, Enum):
    REALTIME = "realtime"      # Event-driven, immediate
    HOURLY = "hourly"
    EVERY_4H = "every_4h"
    DAILY = "daily"
    WEEKLY = "weekly"


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Routine:
    """A scheduled/proactive task an agent performs."""
    name: str
    description: str
    frequency: RoutineFrequency
    celery_task: str              # dotted path to the Celery task
    enabled: bool = True


@dataclass(frozen=True)
class KPI:
    """A key performance indicator tracked per agent."""
    name: str
    description: str
    unit: str                     # "count", "minutes", "percent", "currency"
    target: float | None = None   # target value (None = informational only)
    direction: str = "higher"     # "higher" = better, "lower" = better


@dataclass(frozen=True)
class ApprovalGate:
    """A decision that requires human approval."""
    action: str                   # matches governance policy key
    description: str
    sla_minutes: int
    approver_roles: tuple[str, ...] = ("ops", "executive")


@dataclass(frozen=True)
class AgentCharter:
    """Complete operational definition of a digital team member."""
    agent_type: AgentType
    title: str                    # Human role title (e.g. "Pré-Vendas")
    emoji: str                    # Visual identifier
    role_summary: str             # One-sentence role description
    responsibilities: tuple[str, ...]
    routines: tuple[Routine, ...]
    deliverables: tuple[str, ...]
    kpis: tuple[KPI, ...]
    autonomy: tuple[str, ...]     # What the agent CAN do without approval
    approval_gates: tuple[ApprovalGate, ...]
    communicates_with: tuple[AgentType, ...]  # Other agents it talks to
    business_impact: str          # How it affects revenue/operations
    status: AgentStatus = AgentStatus.ACTIVE


# ── The Digital Team ──────────────────────────────────────────────────────────

SDR_CHARTER = AgentCharter(
    agent_type=AgentType.SDR,
    title="Pré-Vendas (SDR)",
    emoji="🎯",
    role_summary="Qualifica leads inbound e outbound, priorizando os com maior fit para DocAI.",
    responsibilities=(
        "Qualificar todo lead novo em até 30 minutos",
        "Calcular ICP fit score com base em indústria, porte e dor",
        "Classificar leads como qualified/disqualified/nurturing",
        "Escalar leads quentes (score ≥ 70) imediatamente para Sales",
        "Manter enriquecimento de dados do lead atualizado",
    ),
    routines=(
        Routine(
            name="qualify_new_leads",
            description="Qualifica leads que entraram como NEW e não foram processados",
            frequency=RoutineFrequency.HOURLY,
            celery_task="commercial.tasks.qualify_pending_leads_batch",
        ),
        Routine(
            name="stale_lead_alert",
            description="Alerta quando leads quentes ficam >24h sem atividade",
            frequency=RoutineFrequency.EVERY_4H,
            celery_task="agent_runtime.routines.sdr_stale_lead_check",
        ),
    ),
    deliverables=(
        "Lead qualificado com score, ICP fit e razão",
        "Recomendação de próximo passo (demo/nurturing/disqualify)",
        "Enriquecimento de dados no payload do lead",
    ),
    kpis=(
        KPI("leads_qualified_24h", "Leads qualificados nas últimas 24h", "count", target=10, direction="higher"),
        KPI("avg_qualification_time", "Tempo médio de qualificação", "minutes", target=30, direction="lower"),
        KPI("qualification_accuracy", "Taxa de acerto (qualified → opportunity)", "percent", target=60, direction="higher"),
        KPI("hot_lead_response_time", "Tempo de resposta a lead quente", "minutes", target=15, direction="lower"),
    ),
    autonomy=(
        "Qualificar leads automaticamente (score + ICP fit)",
        "Classificar como disqualified se score < 20",
        "Enriquecer payload com dados públicos",
        "Criar nota de qualificação na timeline",
    ),
    approval_gates=(
        ApprovalGate(
            action="commercial.lead.disqualify_high_value",
            description="Desqualificar lead com score > 50 requer aprovação",
            sla_minutes=60,
            approver_roles=("ops",),
        ),
    ),
    communicates_with=(AgentType.SALES, AgentType.JARVIS, AgentType.DOCAI_OPERATOR),
    business_impact="Garante que nenhum lead quente é ignorado e que o time comercial foca nos leads certos. "
                    "Impacto direto no tempo de conversão e na taxa de oportunidades qualificadas.",
)


SALES_CHARTER = AgentCharter(
    agent_type=AgentType.SALES,
    title="Vendedor / Closer",
    emoji="💼",
    role_summary="Converte leads qualificados em oportunidades e conduz até o fechamento.",
    responsibilities=(
        "Gerar follow-up personalizado para leads qualificados",
        "Preparar propostas comerciais com base no perfil",
        "Agendar e preparar demos do DocAI",
        "Acompanhar oportunidades no pipeline",
        "Negociar e ajustar propostas quando necessário",
    ),
    routines=(
        Routine(
            name="followup_qualified_leads",
            description="Gera follow-up para leads qualified sem contato há >12h",
            frequency=RoutineFrequency.EVERY_4H,
            celery_task="agent_runtime.routines.sales_followup_check",
        ),
        Routine(
            name="pipeline_stale_check",
            description="Verifica oportunidades paradas na mesma stage >3 dias",
            frequency=RoutineFrequency.DAILY,
            celery_task="agent_runtime.routines.sales_pipeline_stale_check",
        ),
    ),
    deliverables=(
        "Follow-up personalizado (email/whatsapp) pronto para aprovação",
        "Proposta comercial com pricing e condições",
        "Demo agendada com contexto do lead",
        "Atualização de stage no pipeline",
    ),
    kpis=(
        KPI("followups_sent_7d", "Follow-ups enviados nos últimos 7 dias", "count", target=20, direction="higher"),
        KPI("demo_scheduled_7d", "Demos agendadas nos últimos 7 dias", "count", target=5, direction="higher"),
        KPI("conversion_rate", "Taxa qualified → opportunity", "percent", target=40, direction="higher"),
        KPI("avg_deal_cycle", "Ciclo médio de venda (dias)", "count", target=14, direction="lower"),
        KPI("pipeline_value", "Valor total do pipeline ativo", "currency", direction="higher"),
    ),
    autonomy=(
        "Gerar rascunho de follow-up",
        "Atualizar stage de oportunidade",
        "Preparar contexto para demo",
        "Criar notas na timeline do lead",
    ),
    approval_gates=(
        ApprovalGate(
            action="commercial.followup.send",
            description="Envio de follow-up requer aprovação humana",
            sla_minutes=30,
            approver_roles=("ops", "executive"),
        ),
        ApprovalGate(
            action="commercial.proposal.send",
            description="Envio de proposta comercial requer aprovação",
            sla_minutes=120,
            approver_roles=("ops", "executive"),
        ),
    ),
    communicates_with=(AgentType.SDR, AgentType.DOCAI_OPERATOR, AgentType.JARVIS),
    business_impact="Responsável direto pela receita. Cada follow-up enviado e demo agendada é um passo "
                    "em direção ao fechamento. Pipeline value é o termômetro da saúde comercial.",
)


DOCAI_OPERATOR_CHARTER = AgentCharter(
    agent_type=AgentType.DOCAI_OPERATOR,
    title="Especialista Técnico de Demonstração",
    emoji="📄",
    role_summary="Executa demos do DocAI para leads, gerando insights comerciais a partir da análise de documentos.",
    responsibilities=(
        "Rodar análise DocAI em documentos do lead",
        "Gerar insights comerciais ranqueados com RAG",
        "Preparar contexto técnico para a demo",
        "Sugerir automações DocAI relevantes para o perfil",
        "Documentar qualidade dos insights para melhoria contínua",
    ),
    routines=(
        Routine(
            name="pending_demo_check",
            description="Verifica leads com demo solicitada mas não executada",
            frequency=RoutineFrequency.EVERY_4H,
            celery_task="agent_runtime.routines.docai_pending_demo_check",
        ),
    ),
    deliverables=(
        "Análise DocAI completa com insights ranqueados (score 0-100)",
        "Automações sugeridas por tipo de documento",
        "Contexto RAG com fontes e precedentes",
        "Audit trail com lineage completo da decisão",
    ),
    kpis=(
        KPI("demos_run_7d", "Demos executadas nos últimos 7 dias", "count", target=8, direction="higher"),
        KPI("avg_insight_score", "Score médio dos insights gerados", "count", target=65, direction="higher"),
        KPI("insight_to_demo_conversion", "Taxa de insight → demo agendada", "percent", target=50, direction="higher"),
        KPI("rag_context_quality", "Qtd média de fontes RAG por análise", "count", target=3, direction="higher"),
    ),
    autonomy=(
        "Executar análise DocAI em documento do lead",
        "Gerar insights com RAG pipeline",
        "Classificar tipo de documento",
        "Sugerir automações por tipo",
    ),
    approval_gates=(),  # Demo execution doesn't require approval
    communicates_with=(AgentType.SALES, AgentType.SDR, AgentType.ANALYST),
    business_impact="A demo é o momento decisivo da venda. Insights de qualidade convencem o lead "
                    "de que DocAI resolve seu problema real. Impacto direto na taxa de conversão demo → proposta.",
)


JARVIS_CHARTER = AgentCharter(
    agent_type=AgentType.JARVIS,
    title="Executivo / Orquestrador (Theo)",
    emoji="🧠",
    role_summary="Orquestra toda a operação digital, gera briefings executivos e toma decisões de escalação.",
    responsibilities=(
        "Gerar briefing diário com KPIs comerciais e alertas",
        "Monitorar saúde de toda a operação (agentes, pipeline, aprovações)",
        "Escalar situações críticas (lead quente stale, aprovação expirada)",
        "Coordenar handoffs entre agentes",
        "Reportar métricas consolidadas ao operador humano",
    ),
    routines=(
        Routine(
            name="daily_briefing",
            description="Gera briefing executivo diário com KPIs, alertas e prioridades",
            frequency=RoutineFrequency.DAILY,
            celery_task="agent_runtime.routines.theo_daily_briefing",
        ),
        Routine(
            name="agent_health_check",
            description="Verifica status operacional de todos os agentes",
            frequency=RoutineFrequency.HOURLY,
            celery_task="agent_runtime.routines.theo_agent_health_check",
        ),
        Routine(
            name="escalation_sweep",
            description="Verifica aprovações pendentes e escala se próximo do SLA",
            frequency=RoutineFrequency.HOURLY,
            celery_task="agent_runtime.routines.theo_escalation_sweep",
        ),
    ),
    deliverables=(
        "Briefing executivo diário com KPIs, alertas e top 3 prioridades",
        "Relatório de saúde dos agentes",
        "Escalações automáticas quando SLA próximo",
        "Coordenação de handoffs entre agentes",
    ),
    kpis=(
        KPI("briefing_accuracy", "Precisão do briefing (itens actionable)", "percent", target=80, direction="higher"),
        KPI("escalations_handled", "Escalações tratadas no dia", "count", direction="higher"),
        KPI("avg_decision_time", "Tempo médio entre alerta e ação", "minutes", target=30, direction="lower"),
        KPI("agent_uptime", "Uptime dos agentes da equipe", "percent", target=95, direction="higher"),
    ),
    autonomy=(
        "Gerar briefing executivo",
        "Emitir alertas para o operador",
        "Verificar saúde dos agentes",
        "Sugerir prioridades e próximos passos",
    ),
    approval_gates=(
        ApprovalGate(
            action="executive.alert.broadcast",
            description="Broadcast de alerta crítico para toda a equipe",
            sla_minutes=15,
            approver_roles=("executive",),
        ),
    ),
    communicates_with=(AgentType.SDR, AgentType.SALES, AgentType.DOCAI_OPERATOR, AgentType.SUPPORT, AgentType.ANALYST),
    business_impact="O cérebro da operação. Garante que nada cai entre as rachaduras: "
                    "leads são acionados, aprovações são tratadas, e o operador humano tem visibilidade total.",
)


SUPPORT_CHARTER = AgentCharter(
    agent_type=AgentType.SUPPORT,
    title="Customer Success (CS)",
    emoji="🛡️",
    role_summary="Monitora saúde de clientes ativos, previne churn e maximiza adoção do DocAI.",
    responsibilities=(
        "Monitorar uso do DocAI por clientes ativos",
        "Detectar sinais de churn (queda de uso, tickets frequentes)",
        "Gerar health score por cliente",
        "Propor ações de retenção quando health score cai",
        "Acompanhar onboarding de novos clientes",
    ),
    routines=(
        Routine(
            name="customer_health_check",
            description="Calcula health score de clientes ativos e detecta risco de churn",
            frequency=RoutineFrequency.DAILY,
            celery_task="agent_runtime.routines.cs_customer_health_check",
        ),
        Routine(
            name="onboarding_followup",
            description="Verifica clientes novos (<30 dias) que não completaram onboarding",
            frequency=RoutineFrequency.DAILY,
            celery_task="agent_runtime.routines.cs_onboarding_followup",
        ),
    ),
    deliverables=(
        "Health score por cliente com breakdown",
        "Alertas de risco de churn",
        "Ações de retenção recomendadas",
        "Relatório de adoção do DocAI",
    ),
    kpis=(
        KPI("customer_health_avg", "Health score médio dos clientes", "percent", target=80, direction="higher"),
        KPI("churn_risk_detected", "Riscos de churn detectados no mês", "count", direction="higher"),
        KPI("retention_actions_taken", "Ações de retenção executadas", "count", direction="higher"),
        KPI("onboarding_completion", "Taxa de conclusão de onboarding", "percent", target=90, direction="higher"),
    ),
    autonomy=(
        "Calcular health score",
        "Gerar alertas de churn",
        "Criar notas de acompanhamento",
        "Monitorar métricas de uso",
    ),
    approval_gates=(
        ApprovalGate(
            action="cs.retention.offer",
            description="Ofertas de retenção (desconto, extensão) requerem aprovação",
            sla_minutes=120,
            approver_roles=("ops", "executive"),
        ),
    ),
    communicates_with=(AgentType.JARVIS, AgentType.SALES),
    business_impact="Retenção é mais barata que aquisição. Detectar churn antes que aconteça "
                    "preserva receita recorrente e melhora NPS.",
    status=AgentStatus.STANDBY,  # Will be fully activated in future sprint
)


ANALYST_CHARTER = AgentCharter(
    agent_type=AgentType.ANALYST,
    title="Analista de Dados",
    emoji="📊",
    role_summary="Analisa dados comerciais e operacionais para gerar insights estratégicos.",
    responsibilities=(
        "Analisar conversão do funil (lead → opp → won)",
        "Identificar padrões em leads que convertem",
        "Gerar relatórios de performance da equipe digital",
        "Sugerir otimizações de processo baseadas em dados",
        "Alimentar DocAI Operator com contexto analítico",
    ),
    routines=(
        Routine(
            name="weekly_funnel_report",
            description="Gera relatório semanal do funil com taxas de conversão",
            frequency=RoutineFrequency.WEEKLY,
            celery_task="agent_runtime.routines.analyst_weekly_funnel",
        ),
        Routine(
            name="daily_metrics_snapshot",
            description="Snapshot diário de métricas operacionais",
            frequency=RoutineFrequency.DAILY,
            celery_task="agent_runtime.routines.analyst_daily_metrics",
        ),
    ),
    deliverables=(
        "Relatório semanal do funil com conversion rates",
        "Análise de padrões em leads convertidos",
        "Métricas da equipe digital (performance por agente)",
        "Sugestões de otimização de processo",
    ),
    kpis=(
        KPI("reports_generated_7d", "Relatórios gerados na semana", "count", target=3, direction="higher"),
        KPI("insight_actionability", "Taxa de insights actionable", "percent", target=70, direction="higher"),
        KPI("data_freshness", "Idade média dos dados no relatório", "minutes", target=60, direction="lower"),
    ),
    autonomy=(
        "Gerar relatórios e análises",
        "Calcular métricas e KPIs",
        "Identificar padrões nos dados",
        "Sugerir otimizações",
    ),
    approval_gates=(),
    communicates_with=(AgentType.JARVIS, AgentType.DOCAI_OPERATOR, AgentType.SDR),
    business_impact="Inteligência operacional. Sem dados, decisões são achismo. "
                    "Cada insight actionable melhora o processo comercial.",
)


# ── The INTAKE agent is the receptionist — future expansion ──
INTAKE_CHARTER = AgentCharter(
    agent_type=AgentType.INTAKE,
    title="Recepção / Intake",
    emoji="📥",
    role_summary="Recebe leads de todos os canais e padroniza para entrada no funil.",
    responsibilities=(
        "Receber leads de webhooks (landing, Typeform, HubSpot, etc.)",
        "Normalizar dados de contato e empresa",
        "Verificar duplicatas antes de criar lead",
        "Enriquecer com dados públicos quando possível",
        "Encaminhar imediatamente para SDR qualificar",
    ),
    routines=(
        Routine(
            name="webhook_health_check",
            description="Verifica se webhooks estão recebendo leads normalmente",
            frequency=RoutineFrequency.EVERY_4H,
            celery_task="agent_runtime.routines.intake_webhook_health",
        ),
    ),
    deliverables=(
        "Lead padronizado criado no sistema",
        "Dados de contato normalizados",
        "Deduplicação garantida",
        "SDR notificado para qualificar",
    ),
    kpis=(
        KPI("leads_received_24h", "Leads recebidos nas últimas 24h", "count", direction="higher"),
        KPI("dedup_rate", "Taxa de duplicatas detectadas", "percent", direction="higher"),
        KPI("normalization_success", "Taxa de normalização com sucesso", "percent", target=95, direction="higher"),
        KPI("intake_to_sdr_time", "Tempo entre intake e SDR pickup", "minutes", target=5, direction="lower"),
    ),
    autonomy=(
        "Criar lead a partir de webhook",
        "Normalizar dados de contato",
        "Detectar e marcar duplicatas",
        "Encaminhar para SDR via inter-agent bus",
    ),
    approval_gates=(),
    communicates_with=(AgentType.SDR, AgentType.JARVIS),
    business_impact="Porta de entrada de toda receita futura. Lead que entra mal formatado "
                    "ou duplicado gera ruído e desperdício em toda a cadeia.",
)


# ── Registry ──────────────────────────────────────────────────────────────────

AGENT_TEAM: dict[AgentType, AgentCharter] = {
    AgentType.JARVIS: JARVIS_CHARTER,
    AgentType.INTAKE: INTAKE_CHARTER,
    AgentType.SDR: SDR_CHARTER,
    AgentType.SALES: SALES_CHARTER,
    AgentType.DOCAI_OPERATOR: DOCAI_OPERATOR_CHARTER,
    AgentType.SUPPORT: SUPPORT_CHARTER,
    AgentType.ANALYST: ANALYST_CHARTER,
}


def get_charter(agent_type: AgentType) -> AgentCharter:
    """Return the charter for the given agent type."""
    return AGENT_TEAM[agent_type]


def get_active_team() -> list[AgentCharter]:
    """Return all team members with ACTIVE status."""
    return [c for c in AGENT_TEAM.values() if c.status == AgentStatus.ACTIVE]


def get_team_summary() -> list[dict]:
    """
    Return a serializable summary of the entire digital team.
    Used by the executive briefing and the /ops/team dashboard.
    """
    result = []
    for charter in AGENT_TEAM.values():
        result.append({
            "agent_type": charter.agent_type.value,
            "title": charter.title,
            "emoji": charter.emoji,
            "role_summary": charter.role_summary,
            "status": charter.status.value,
            "responsibilities_count": len(charter.responsibilities),
            "routines_count": len(charter.routines),
            "routines_enabled": sum(1 for r in charter.routines if r.enabled),
            "kpis_count": len(charter.kpis),
            "approval_gates_count": len(charter.approval_gates),
            "communicates_with": [a.value for a in charter.communicates_with],
            "business_impact": charter.business_impact,
        })
    return result


def get_charter_detail(agent_type: AgentType) -> dict:
    """
    Return full charter as a serializable dict.
    Used by the agent detail page in the ops dashboard.
    """
    c = AGENT_TEAM[agent_type]
    return {
        "agent_type": c.agent_type.value,
        "title": c.title,
        "emoji": c.emoji,
        "role_summary": c.role_summary,
        "status": c.status.value,
        "responsibilities": list(c.responsibilities),
        "routines": [
            {
                "name": r.name,
                "description": r.description,
                "frequency": r.frequency.value,
                "celery_task": r.celery_task,
                "enabled": r.enabled,
            }
            for r in c.routines
        ],
        "deliverables": list(c.deliverables),
        "kpis": [
            {
                "name": k.name,
                "description": k.description,
                "unit": k.unit,
                "target": k.target,
                "direction": k.direction,
            }
            for k in c.kpis
        ],
        "autonomy": list(c.autonomy),
        "approval_gates": [
            {
                "action": g.action,
                "description": g.description,
                "sla_minutes": g.sla_minutes,
                "approver_roles": list(g.approver_roles),
            }
            for g in c.approval_gates
        ],
        "communicates_with": [a.value for a in c.communicates_with],
        "business_impact": c.business_impact,
    }
