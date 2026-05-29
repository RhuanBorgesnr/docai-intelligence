"""REST API for the commercial domain (Sprint 4 / B1, B6, Phase 2).

All commercial endpoints are internal-ops only — require ``is_staff`` in production.
"""
from __future__ import annotations

from django.db.models import Avg, Count, Sum
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from commercial.enums import (
    ACTIVE_OPPORTUNITY_STAGES,
    LeadStatus,
    OpportunityStage,
)
from commercial.models import FollowUpDraft, Lead, Opportunity
from commercial.serializers import (
    FollowUpDraftSerializer,
    FollowUpRequestSerializer,
    LeadIngestionSerializer,
    LeadSerializer,
    OpportunitySerializer,
    OpportunityStageUpdateSerializer,
)
from commercial.services import (
    draft_followup,
    ingest_lead,
    qualify_lead,
    transition_opportunity,
)
from core.tenants import INTERNAL_TENANT_ID


# ── Ingestion ────────────────────────────────────────────────────────────────

class LeadIngestionView(APIView):
    """POST /api/commercial/leads/  — manual / form / CSV ingestion."""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = LeadIngestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ingest_lead(**serializer.validated_data)
        body = {
            "created": result.created,
            "lead": LeadSerializer(result.lead).data,
            "score_breakdown": result.score.to_dict(),
        }
        return Response(
            body,
            status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
        )


class LeadWebhookView(APIView):
    """POST /api/commercial/leads/webhook/<source>/  — public webhook for inbound leads.

    Accepts leads from any source (landing page, Typeform, HubSpot, etc.).
    Uses the Intake agent's normalizer and optional HMAC verification.
    """
    permission_classes = [AllowAny]

    def post(self, request, source: str, *args, **kwargs):
        from commercial.webhooks import handle_webhook
        from django.conf import settings as django_settings

        payload = dict(request.data)

        # HMAC verification (if configured)
        hmac_secret = getattr(django_settings, 'WEBHOOK_HMAC_SECRETS', {}).get(source)
        signature = request.headers.get('X-Webhook-Signature', '')
        raw_body = request.body if hmac_secret else None

        result = handle_webhook(
            source=source,
            payload=payload,
            raw_body=raw_body,
            signature=signature,
            hmac_secret=hmac_secret,
        )

        if "error" in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"created": result["created"], "lead_id": result["lead_id"], "score": result["score"]},
            status=status.HTTP_201_CREATED if result["created"] else status.HTTP_200_OK,
        )


# ── Leads ────────────────────────────────────────────────────────────────────

class LeadListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadSerializer

    def get_queryset(self):
        qs = Lead.objects.all().order_by("-score", "-created_at")
        tenant = self.request.query_params.get("tenant_id", INTERNAL_TENANT_ID)
        qs = qs.filter(tenant_id=tenant)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        min_score = self.request.query_params.get("min_score")
        if min_score:
            try:
                qs = qs.filter(score__gte=int(min_score))
            except ValueError:
                pass
        return qs


class LeadDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadSerializer
    queryset = Lead.objects.all()
    lookup_field = "lead_id"


class LeadQualifyView(APIView):
    """POST /api/commercial/leads/<lead_id>/qualify/ — re-run SDR Agent."""
    permission_classes = [IsAuthenticated]

    def post(self, request, lead_id: str, *args, **kwargs):
        lead = generics.get_object_or_404(Lead, lead_id=lead_id)
        outcome = qualify_lead(lead.id)
        agent_info = {}
        if outcome.agent_result and outcome.agent_result.metrics:
            m = outcome.agent_result.metrics
            agent_info = {
                "provider": getattr(outcome.agent_result.metrics, '_provider', 'groq'),
                "status": outcome.agent_result.status.value,
                "tokens": m.total_tokens,
                "latency_ms": round(m.llm_latency_ms, 1),
                "retries": m.retry_count,
            }
        return Response({
            "lead": LeadSerializer(outcome.lead).data,
            "qualified": outcome.qualified,
            "confidence": outcome.confidence,
            "reason": outcome.reason,
            "opportunity": (
                OpportunitySerializer(outcome.opportunity).data
                if outcome.opportunity else None
            ),
            "agent": agent_info,
        })


class LeadFollowupView(APIView):
    """POST /api/commercial/leads/<lead_id>/followup/ — draft + request approval."""
    permission_classes = [IsAuthenticated]

    def post(self, request, lead_id: str, *args, **kwargs):
        lead = generics.get_object_or_404(Lead, lead_id=lead_id)
        serializer = FollowUpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        draft = draft_followup(lead, **serializer.validated_data)
        return Response(FollowUpDraftSerializer(draft).data, status=status.HTTP_201_CREATED)


# ── Opportunities (pipeline) ─────────────────────────────────────────────────

class OpportunityListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OpportunitySerializer

    def get_queryset(self):
        qs = Opportunity.objects.select_related("lead").all().order_by("-created_at")
        tenant = self.request.query_params.get("tenant_id", INTERNAL_TENANT_ID)
        qs = qs.filter(tenant_id=tenant)
        stage = self.request.query_params.get("stage")
        if stage:
            qs = qs.filter(stage=stage)
        active = self.request.query_params.get("active")
        if active and active.lower() in ("1", "true", "yes"):
            qs = qs.filter(stage__in=ACTIVE_OPPORTUNITY_STAGES)
        return qs


class OpportunityDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OpportunitySerializer
    queryset = Opportunity.objects.select_related("lead").all()
    lookup_field = "opportunity_id"


class OpportunityStageView(APIView):
    """POST /api/commercial/opportunities/<id>/stage/  — move stage."""
    permission_classes = [IsAuthenticated]

    def post(self, request, opportunity_id: str, *args, **kwargs):
        opp = generics.get_object_or_404(Opportunity, opportunity_id=opportunity_id)
        serializer = OpportunityStageUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        opp = transition_opportunity(
            opp,
            new_stage=serializer.validated_data["stage"],
            actor_id=str(request.user.id) if request.user.is_authenticated else "system",
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(OpportunitySerializer(opp).data)


# ── Pipeline summary (B6) ────────────────────────────────────────────────────

class CommercialPipelineSummaryView(APIView):
    """GET /api/commercial/pipeline/  — kanban data + KPIs."""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        tenant = request.query_params.get("tenant_id", INTERNAL_TENANT_ID)
        opps = Opportunity.objects.filter(tenant_id=tenant)

        by_stage = {stage.value: [] for stage in OpportunityStage}
        stage_value: dict[str, float] = {stage.value: 0.0 for stage in OpportunityStage}
        for opp in opps.select_related("lead"):
            by_stage[opp.stage].append({
                "opportunity_id": opp.opportunity_id,
                "lead_id": opp.lead.lead_id,
                "company_name": opp.lead.company_name,
                "score": opp.lead.score,
                "estimated_value": float(opp.estimated_value),
                "win_probability": opp.win_probability,
                "stage": opp.stage,
            })
            stage_value[opp.stage] += float(opp.estimated_value)

        leads_qs = Lead.objects.filter(tenant_id=tenant)
        leads_by_status = dict(
            leads_qs.values_list("status").annotate(c=Count("id")).values_list("status", "c")
        )

        active_value = sum(
            stage_value[s] for s in ACTIVE_OPPORTUNITY_STAGES
        )
        won_value = stage_value.get(OpportunityStage.WON, 0.0)
        lost_value = stage_value.get(OpportunityStage.LOST, 0.0)

        return Response({
            "tenant_id": tenant,
            "kpis": {
                "leads_total": leads_qs.count(),
                "leads_qualified": leads_by_status.get(LeadStatus.QUALIFIED, 0)
                + leads_by_status.get(LeadStatus.CONVERTED, 0),
                "leads_disqualified": leads_by_status.get(LeadStatus.DISQUALIFIED, 0),
                "opportunities_active": opps.filter(stage__in=ACTIVE_OPPORTUNITY_STAGES).count(),
                "opportunities_won": opps.filter(stage=OpportunityStage.WON).count(),
                "opportunities_lost": opps.filter(stage=OpportunityStage.LOST).count(),
                "pipeline_value_active": active_value,
                "pipeline_value_won": won_value,
                "pipeline_value_lost": lost_value,
                "avg_lead_score": leads_qs.aggregate(a=Avg("score"))["a"] or 0,
            },
            "by_stage": by_stage,
            "stage_value": stage_value,
            "leads_by_status": leads_by_status,
        })


class HotLeadsView(APIView):
    """GET /api/commercial/leads/hot/  — top scoring qualified-but-not-converted leads."""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        tenant = request.query_params.get("tenant_id", INTERNAL_TENANT_ID)
        limit = int(request.query_params.get("limit", 10))
        qs = (
            Lead.objects.filter(tenant_id=tenant)
            .filter(score__gte=70)
            .exclude(status=LeadStatus.DISQUALIFIED)
            .order_by("-score", "-last_event_at")[:limit]
        )
        return Response({"count": qs.count(), "leads": LeadSerializer(qs, many=True).data})


class FollowUpDraftListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FollowUpDraftSerializer

    def get_queryset(self):
        qs = FollowUpDraft.objects.select_related("lead").all().order_by("-created_at")
        tenant = self.request.query_params.get("tenant_id", INTERNAL_TENANT_ID)
        qs = qs.filter(tenant_id=tenant)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class DocAIDemoView(APIView):
    """POST /api/commercial/leads/<lead_id>/docai-demo/  — run DocAI Operator."""
    permission_classes = [IsAuthenticated]

    def post(self, request, lead_id: str, *args, **kwargs):
        from commercial.docai_operator import run_docai_demo

        lead = generics.get_object_or_404(Lead, lead_id=lead_id)
        document_id = request.data.get("document_id")
        if not document_id:
            return Response(
                {"error": "document_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = run_docai_demo(lead_id=lead.id, document_id=int(document_id))
        except Exception as exc:  # noqa: BLE001
            return Response(
                {"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        return Response(result, status=status.HTTP_200_OK)


class LeadDocumentUploadView(APIView):
    """POST /api/commercial/leads/<lead_id>/documents/  — upload a document for this lead."""
    permission_classes = [IsAuthenticated]

    def post(self, request, lead_id: str, *args, **kwargs):
        from documents.models import Document

        lead = generics.get_object_or_404(Lead, lead_id=lead_id)
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"error": "file is required"}, status=status.HTTP_400_BAD_REQUEST)

        doc = Document.objects.create(
            file=uploaded_file,
            title=request.data.get("title", uploaded_file.name),
            document_type=request.data.get("document_type", "other"),
        )

        # Link document to lead payload for future reference
        payload = dict(lead.payload or {})
        doc_list = payload.get("documents", [])
        doc_list.append({"document_id": doc.id, "title": doc.title, "type": doc.document_type})
        payload["documents"] = doc_list
        lead.payload = payload
        lead.save(update_fields=["payload", "updated_at"])

        return Response({
            "document_id": doc.id,
            "title": doc.title,
            "document_type": doc.document_type,
            "processing_status": doc.processing_status,
        }, status=status.HTTP_201_CREATED)


class LeadDocumentsListView(APIView):
    """GET /api/commercial/leads/<lead_id>/documents/  — list documents linked to this lead."""
    permission_classes = [IsAuthenticated]

    def get(self, request, lead_id: str, *args, **kwargs):
        from documents.models import Document

        lead = generics.get_object_or_404(Lead, lead_id=lead_id)
        doc_refs = (lead.payload or {}).get("documents", [])
        doc_ids = [d["document_id"] for d in doc_refs if "document_id" in d]
        docs = Document.objects.filter(id__in=doc_ids).order_by("-created_at")
        results = [
            {
                "document_id": d.id,
                "title": d.title,
                "document_type": d.document_type,
                "processing_status": d.processing_status,
                "created_at": d.created_at.isoformat(),
            }
            for d in docs
        ]
        return Response({"count": len(results), "documents": results})


class LeadInsightsView(APIView):
    """GET /api/commercial/leads/<lead_id>/insights/  — all DocAI insights generated for this lead."""
    permission_classes = [IsAuthenticated]

    def get(self, request, lead_id: str, *args, **kwargs):
        lead = generics.get_object_or_404(Lead, lead_id=lead_id)
        insights_history = (lead.payload or {}).get("docai_insights", [])
        return Response({
            "lead_id": lead.lead_id,
            "count": len(insights_history),
            "insights": list(reversed(insights_history)),  # newest first
        })


class LeadTimelineView(APIView):
    """GET /api/commercial/leads/<lead_id>/timeline/  — audit + case events timeline."""
    permission_classes = [IsAuthenticated]

    def get(self, request, lead_id: str, *args, **kwargs):
        from audit.models import AuditLog
        from orchestrator.models import CaseEvent

        lead = generics.get_object_or_404(Lead, lead_id=lead_id)
        timeline = []

        # Case events
        if lead.case_id:
            for evt in CaseEvent.objects.filter(case_id=lead.case_id).order_by("-occurred_at")[:30]:
                timeline.append({
                    "type": "event",
                    "event_type": evt.event_type,
                    "source": evt.source,
                    "payload": evt.payload,
                    "timestamp": evt.occurred_at.isoformat(),
                })

            # Audit entries
            for log in AuditLog.objects.filter(case_id=lead.case_id).order_by("-created_at")[:30]:
                timeline.append({
                    "type": "audit",
                    "action": log.action,
                    "actor_type": log.actor_type,
                    "actor_id": log.actor_id,
                    "details": log.details,
                    "timestamp": log.created_at.isoformat(),
                })

        # Score events
        for se in lead.score_events.order_by("-created_at")[:20]:
            timeline.append({
                "type": "score_change",
                "score_before": se.score_before,
                "score_after": se.score_after,
                "reason": se.reason,
                "timestamp": se.created_at.isoformat(),
            })

        timeline.sort(key=lambda x: x["timestamp"], reverse=True)
        return Response({"lead_id": lead.lead_id, "count": len(timeline), "events": timeline[:50]})


# ── Agent Team (Phase 3) ─────────────────────────────────────────────────────

class AgentTeamView(APIView):
    """GET /api/commercial/agents/team/  — digital team org chart."""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from agent_runtime.agent_charter import get_team_summary
        return Response({"team": get_team_summary()})


class AgentDetailView(APIView):
    """GET /api/commercial/agents/<agent_type>/  — full charter + live KPIs."""
    permission_classes = [IsAuthenticated]

    def get(self, request, agent_type: str, *args, **kwargs):
        from agent_runtime.prompt_registry import AgentType as AT
        from agent_runtime.agent_charter import get_charter_detail
        from agent_runtime.agent_metrics import compute_agent_metrics

        try:
            at = AT(agent_type)
        except ValueError:
            return Response({"error": f"Unknown agent: {agent_type}"}, status=status.HTTP_404_NOT_FOUND)

        charter = get_charter_detail(at)
        metrics = compute_agent_metrics(at)
        return Response({"charter": charter, "metrics": metrics})


class AgentRunRoutineView(APIView):
    """POST /api/commercial/agents/<agent_type>/routine/<routine_name>/  — trigger a routine manually."""
    permission_classes = [IsAdminUser]

    def post(self, request, agent_type: str, routine_name: str, *args, **kwargs):
        from agent_runtime.prompt_registry import AgentType as AT
        from agent_runtime.agent_charter import get_charter
        import importlib

        try:
            at = AT(agent_type)
        except ValueError:
            return Response({"error": f"Unknown agent: {agent_type}"}, status=status.HTTP_404_NOT_FOUND)

        charter = get_charter(at)
        routine = next((r for r in charter.routines if r.name == routine_name), None)
        if not routine:
            return Response(
                {"error": f"Routine '{routine_name}' not found for agent {agent_type}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Import and call the routine function
        module_path, func_name = routine.celery_task.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
            fn = getattr(module, func_name)
            result = fn()
        except Exception as exc:  # noqa: BLE001
            return Response(
                {"error": str(exc), "routine": routine_name},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"routine": routine_name, "agent": agent_type, "result": result})


class ScheduleDemoView(APIView):
    """POST /api/commercial/leads/<lead_id>/schedule-demo/  — schedule a DocAI demo."""
    permission_classes = [IsAuthenticated]

    def post(self, request, lead_id: str, *args, **kwargs):
        from commercial.demo_scheduler import schedule_demo
        from datetime import datetime

        scheduled_at = None
        if request.data.get("scheduled_at"):
            try:
                scheduled_at = datetime.fromisoformat(request.data["scheduled_at"])
            except (ValueError, TypeError):
                return Response(
                    {"error": "Invalid scheduled_at format (use ISO 8601)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            result = schedule_demo(
                lead_id=lead_id,
                scheduled_at=scheduled_at,
                notes=request.data.get("notes", ""),
                scheduled_by=request.user.username if hasattr(request.user, "username") else "ops",
            )
        except Lead.DoesNotExist:
            return Response({"error": "Lead not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:  # noqa: BLE001
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(result, status=status.HTTP_201_CREATED)
