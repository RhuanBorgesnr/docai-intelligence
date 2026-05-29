"""API views for Jarvis orchestrator."""
from __future__ import annotations

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditLog
from audit.services import write_audit_log
from orchestrator.models import Case, CaseEvent
from orchestrator.serializers import (
    AuditLogSerializer,
    CaseEventSerializer,
    CaseSerializer,
    EventIngestionSerializer,
)
from orchestrator.services import ingest_event
from orchestrator.tasks import process_received_event


class EventIngestionView(APIView):
    """Receives external/internal events and queues workflow processing."""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = EventIngestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ingest_event(data=serializer.validated_data)

        if result.created:
            try:
                process_received_event.delay(result.event.id)
            except Exception:
                # Fallback for local/dev when broker is not available.
                process_received_event(result.event.id)

            write_audit_log(
                action="case.created" if result.event.case.events.count() == 1 else "case.updated",
                case_id=result.event.case_id,
                trace_id=result.event.trace_id,
                correlation_id=result.event.correlation_id,
                details={"event_id": result.event.event_id},
            )

        payload = {
            "created": result.created,
            "case": CaseSerializer(result.event.case).data,
            "event": CaseEventSerializer(result.event).data,
        }
        return Response(payload, status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK)


class CaseListView(generics.ListAPIView):
    """List orchestration cases."""

    permission_classes = [IsAuthenticated]
    serializer_class = CaseSerializer

    def get_queryset(self):
        return Case.objects.all().order_by("-created_at")


class CaseDetailView(generics.RetrieveAPIView):
    """Retrieve a case by id."""

    permission_classes = [IsAuthenticated]
    serializer_class = CaseSerializer
    queryset = Case.objects.all()


class CaseEventListView(generics.ListAPIView):
    """List all events for one case."""

    permission_classes = [IsAuthenticated]
    serializer_class = CaseEventSerializer

    def get_queryset(self):
        case_id = self.kwargs["case_id"]
        return CaseEvent.objects.filter(case_id=case_id).order_by("created_at")


class CaseAuditLogListView(generics.ListAPIView):
    """List audit logs for one case."""

    permission_classes = [IsAuthenticated]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        case_id = self.kwargs["case_id"]
        return AuditLog.objects.filter(case_id=case_id).order_by("-created_at")


# ── Operational Dashboard ────────────────────────────────────────────────────

class OperationalDashboardView(APIView):
    """Full operational dashboard (pipeline + approvals + notifications + health)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from orchestrator.dashboard import get_operational_summary

        tenant_id = request.query_params.get("tenant_id")
        data = get_operational_summary(tenant_id=tenant_id)
        return Response(data)


class CasePipelineView(APIView):
    """Case pipeline breakdown by state, priority, workflow status."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from orchestrator.dashboard import get_case_pipeline

        tenant_id = request.query_params.get("tenant_id")
        return Response(get_case_pipeline(tenant_id=tenant_id))


class CaseThroughputView(APIView):
    """Case creation/completion throughput over a period."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from orchestrator.dashboard import get_case_throughput

        tenant_id = request.query_params.get("tenant_id")
        days = int(request.query_params.get("days", 30))
        return Response(get_case_throughput(days=days, tenant_id=tenant_id))


class ApprovalSummaryView(APIView):
    """Approval queue metrics."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from orchestrator.dashboard import get_approval_summary

        tenant_id = request.query_params.get("tenant_id")
        return Response(get_approval_summary(tenant_id=tenant_id))


class NotificationMetricsView(APIView):
    """Notification delivery statistics."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from orchestrator.dashboard import get_notification_metrics

        tenant_id = request.query_params.get("tenant_id")
        return Response(get_notification_metrics(tenant_id=tenant_id))


class SystemHealthView(APIView):
    """System health: circuit breakers, DLQ, pending queues."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from orchestrator.dashboard import get_system_health

        return Response(get_system_health())


class AgentStatusView(APIView):
    """Agent topology with live status for the visual operations dashboard."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from orchestrator.dashboard import get_agent_status

        tenant_id = request.query_params.get("tenant_id")
        return Response(get_agent_status(tenant_id=tenant_id))


# ── Jarvis Executive Endpoints ───────────────────────────────────────────────

class JarvisBriefingView(APIView):
    """GET executive briefing — KPIs, alerts, recommendations."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from orchestrator.jarvis_agent import JarvisAgent

        tenant_id = request.query_params.get("tenant_id")
        jarvis = JarvisAgent()
        briefing = jarvis.generate_briefing(tenant_id=tenant_id)
        return Response(briefing)


class JarvisAskView(APIView):
    """POST natural-language question → Jarvis answer with context."""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        from django.utils import timezone as tz

        question = (request.data.get("question") or "").strip()
        if not question:
            return Response(
                {"error": "O campo 'question' é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build answer using available tools
        from orchestrator.jarvis_agent import JarvisAgent

        jarvis = JarvisAgent()
        briefing = jarvis.generate_briefing()

        # Simple rule-based intent detection + answer construction
        answer, references = _answer_question(question, briefing)

        return Response({
            "question": question,
            "answer": answer,
            "references": references,
            "context_used": list(references.keys()) if isinstance(references, dict) else [],
            "generated_at": tz.now().isoformat(),
        })


def _answer_question(question: str, briefing: dict) -> tuple[str, dict]:
    """
    Simple intent-based answering from the briefing data.
    Returns (answer_text, references_dict).
    """
    q = question.lower()
    refs: dict = {}
    summary = briefing.get("summary", {})
    alerts = briefing.get("alerts", [])

    # Intent: alerts / problemas
    if any(w in q for w in ("alerta", "problema", "issue", "erro", "falha")):
        if alerts:
            answer = f"Encontrei {len(alerts)} alerta(s):\n" + "\n".join(f"• {a}" for a in alerts)
        else:
            answer = "Nenhum alerta ativo no momento. Todos os sistemas estão operando normalmente."
        refs["alerts"] = alerts
        return answer, refs

    # Intent: cases / pipeline
    if any(w in q for w in ("case", "caso", "pipeline", "fila", "ativo")):
        active = summary.get("active_cases", 0)
        created = summary.get("created_30d", 0)
        completed = summary.get("completed_30d", 0)
        answer = (
            f"Pipeline atual:\n"
            f"• {active} case(s) ativo(s)\n"
            f"• {created} criado(s) nos últimos 30 dias\n"
            f"• {completed} concluído(s) nos últimos 30 dias"
        )
        if summary.get("avg_resolution_hours"):
            answer += f"\n• Tempo médio de resolução: {summary['avg_resolution_hours']:.1f}h"
        refs["pipeline"] = briefing.get("pipeline_breakdown", {})
        return answer, refs

    # Intent: approvals
    if any(w in q for w in ("aprovação", "aprovacao", "approval", "pendente")):
        pending = summary.get("pending_approvals", 0)
        overdue = summary.get("overdue_approvals", 0)
        answer = f"Aprovações: {pending} pendente(s)"
        if overdue:
            answer += f", {overdue} vencida(s) ⚠️"
        else:
            answer += " — todas dentro do prazo."
        refs["approvals"] = {"pending": pending, "overdue": overdue}
        return answer, refs

    # Intent: notifications
    if any(w in q for w in ("notificação", "notificacao", "notification", "email", "whatsapp")):
        pending_n = summary.get("pending_notifications", 0)
        answer = f"Notificações pendentes: {pending_n}."
        if any("notificação" in a.lower() or "falharam" in a.lower() for a in alerts):
            answer += " ⚠️ Há alertas de falha em notificações."
        refs["notifications"] = {"pending": pending_n}
        return answer, refs

    # Intent: resumo / briefing
    if any(w in q for w in ("resumo", "briefing", "status", "geral", "overview", "como está")):
        parts = [
            f"📊 Briefing Executivo:",
            f"• Cases ativos: {summary.get('active_cases', 0)}",
            f"• Criados (30d): {summary.get('created_30d', 0)}",
            f"• Concluídos (30d): {summary.get('completed_30d', 0)}",
            f"• Aprovações pendentes: {summary.get('pending_approvals', 0)}",
            f"• Notificações pendentes: {summary.get('pending_notifications', 0)}",
        ]
        if alerts:
            parts.append(f"\n⚠️ {len(alerts)} alerta(s): " + "; ".join(alerts[:3]))
        else:
            parts.append("\n✅ Nenhum alerta ativo.")
        answer = "\n".join(parts)
        refs["summary"] = summary
        refs["alerts"] = alerts
        return answer, refs

    # Fallback
    answer = (
        f"Aqui está um resumo rápido: {summary.get('active_cases', 0)} case(s) ativo(s), "
        f"{summary.get('pending_approvals', 0)} aprovação(ões) pendente(s), "
        f"{len(alerts)} alerta(s). "
        f"Tente perguntar sobre 'alertas', 'cases', 'aprovações', 'notificações' ou 'resumo'."
    )
    refs["summary"] = summary
    return answer, refs
