"""
Daily Operations API — what happened today, what needs attention, costs.

This is what makes /ops feel like a REAL operational cockpit.
Returns everything the operator needs to run the company every morning.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class DailyOpsView(APIView):
    """GET /api/ops/daily/ — morning briefing data.

    Returns:
    - today: new leads, follow-ups sent, approvals pending/decided, executions
    - costs: today/week/month totals + per-agent breakdown
    - actions_needed: things that require human attention NOW
    - recent_activity: last 20 events across the system
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)

        data = {
            "generated_at": now.isoformat(),
            "today": self._today_stats(today_start),
            "costs": self._cost_stats(today_start, week_start, month_start),
            "actions_needed": self._actions_needed(),
            "recent_activity": self._recent_activity(today_start),
            "agent_activity": self._agent_activity_today(today_start),
        }
        return Response(data)

    def _today_stats(self, today_start) -> dict:
        from commercial.models import Lead, FollowUpDraft, Opportunity
        from approvals.models import Approval

        new_leads = Lead.objects.filter(created_at__gte=today_start).count()
        total_leads = Lead.objects.count()
        qualified_today = Lead.objects.filter(
            status="qualified", updated_at__gte=today_start
        ).count()

        followups_sent = FollowUpDraft.objects.filter(
            sent_at__gte=today_start
        ).count()
        followups_pending = FollowUpDraft.objects.filter(
            status="pending_approval"
        ).count()

        approvals_pending = Approval.objects.filter(status="pending").count()
        approvals_decided_today = Approval.objects.filter(
            decided_at__gte=today_start
        ).count()

        active_opportunities = Opportunity.objects.exclude(
            stage__in=["closed_won", "closed_lost"]
        ).count()

        return {
            "new_leads": new_leads,
            "total_leads": total_leads,
            "qualified_today": qualified_today,
            "followups_sent": followups_sent,
            "followups_pending": followups_pending,
            "approvals_pending": approvals_pending,
            "approvals_decided_today": approvals_decided_today,
            "active_opportunities": active_opportunities,
        }

    def _cost_stats(self, today_start, week_start, month_start) -> dict:
        try:
            from agent_runtime.cost_tracker import AgentExecution
        except Exception:
            return {"today_usd": 0, "week_usd": 0, "month_usd": 0, "per_agent": []}

        def _agg(since):
            qs = AgentExecution.objects.filter(created_at__gte=since)
            r = qs.aggregate(
                cost=Sum("estimated_cost_usd"),
                tokens=Sum("total_tokens"),
                execs=Count("id"),
            )
            return {
                "cost_usd": round(r["cost"] or 0, 4),
                "tokens": r["tokens"] or 0,
                "executions": r["execs"] or 0,
            }

        per_agent = list(
            AgentExecution.objects.filter(created_at__gte=week_start)
            .values("agent_type")
            .annotate(
                cost=Sum("estimated_cost_usd"),
                tokens=Sum("total_tokens"),
                executions=Count("id"),
                avg_latency=Avg("latency_ms"),
            )
            .order_by("-cost")
        )

        return {
            "today": _agg(today_start),
            "week": _agg(week_start),
            "month": _agg(month_start),
            "per_agent": per_agent,
        }

    def _actions_needed(self) -> list:
        """Things that need human attention RIGHT NOW."""
        actions = []
        from approvals.models import Approval
        from commercial.models import Lead, FollowUpDraft

        # Pending approvals
        pending = Approval.objects.filter(status="pending").count()
        if pending:
            actions.append({
                "type": "approval",
                "icon": "✅",
                "title": f"{pending} aprovação(ões) pendente(s)",
                "action": "Revisar em /ops/approvals",
                "link": "/ops/approvals",
                "priority": "high",
            })

        # Hot leads without follow-up
        hot_no_followup = Lead.objects.filter(
            score__gte=70, status__in=["new", "qualified"]
        ).exclude(
            lead_id__in=FollowUpDraft.objects.values_list("lead__lead_id", flat=True)
        ).count()
        if hot_no_followup:
            actions.append({
                "type": "followup",
                "icon": "🔥",
                "title": f"{hot_no_followup} lead(s) quente(s) sem follow-up",
                "action": "Gerar follow-up em /ops/leads",
                "link": "/ops/leads",
                "priority": "high",
            })

        # Stale leads (no activity in 3+ days)
        stale_cutoff = timezone.now() - timedelta(days=3)
        stale = Lead.objects.filter(
            status__in=["new", "qualified"],
            updated_at__lt=stale_cutoff,
        ).count()
        if stale:
            actions.append({
                "type": "stale",
                "icon": "⏰",
                "title": f"{stale} lead(s) parado(s) há 3+ dias",
                "action": "Re-qualificar ou descartar",
                "link": "/ops/leads",
                "priority": "medium",
            })

        # Pending follow-ups not yet sent
        unsent = FollowUpDraft.objects.filter(
            status__in=["approved", "pending_approval"]
        ).count()
        if unsent:
            actions.append({
                "type": "send",
                "icon": "📧",
                "title": f"{unsent} follow-up(s) aguardando envio",
                "action": "Aprovar e enviar",
                "link": "/ops/approvals",
                "priority": "medium",
            })

        return actions

    def _recent_activity(self, today_start) -> list:
        """Last 20 events from audit log."""
        from audit.models import AuditLog

        events = AuditLog.objects.filter(
            created_at__gte=today_start
        ).order_by("-created_at")[:20]

        return [
            {
                "action": e.action,
                "actor": e.actor_id or e.actor_type,
                "details": e.details if isinstance(e.details, dict) else {},
                "at": e.created_at.isoformat(),
            }
            for e in events
        ]

    def _agent_activity_today(self, today_start) -> list:
        """Per-agent execution summary for today."""
        try:
            from agent_runtime.cost_tracker import AgentExecution
        except Exception:
            return []

        return list(
            AgentExecution.objects.filter(created_at__gte=today_start)
            .values("agent_type")
            .annotate(
                executions=Count("id"),
                successes=Count("id", filter=Q(status="success")),
                failures=Count("id", filter=Q(status="failed")),
                tokens=Sum("total_tokens"),
                cost=Sum("estimated_cost_usd"),
                avg_latency=Avg("latency_ms"),
            )
            .order_by("-executions")
        )


class CostSummaryView(APIView):
    """GET /api/ops/costs/?days=7 — cost breakdown."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        days = int(request.query_params.get("days", 7))
        try:
            from agent_runtime.cost_tracker import cost_summary
            return Response(cost_summary(days=days))
        except Exception as e:
            return Response({"error": str(e)}, status=500)


class AgentPerformanceView(APIView):
    """GET /api/ops/agents/<type>/performance/?days=7 — agent refinement data."""
    permission_classes = [IsAuthenticated]

    def get(self, request, agent_type: str):
        days = int(request.query_params.get("days", 7))
        try:
            from agent_runtime.cost_tracker import agent_performance
            return Response(agent_performance(agent_type, days=days))
        except Exception as e:
            return Response({"error": str(e)}, status=500)


class ExecutionFeedbackView(APIView):
    """POST /api/ops/executions/<id>/feedback/ — rate an agent output."""
    permission_classes = [IsAuthenticated]

    def post(self, request, execution_id: str):
        from agent_runtime.cost_tracker import record_feedback

        quality = request.data.get("quality")
        useful = request.data.get("useful")
        notes = request.data.get("notes", "")
        by = request.user.username if request.user else ""

        ok = record_feedback(
            execution_id=execution_id,
            quality=int(quality) if quality is not None else None,
            useful=useful,
            notes=notes,
            by=by,
        )
        if ok:
            return Response({"status": "recorded"})
        return Response({"error": "Execution not found"}, status=404)


class SystemStatusView(APIView):
    """GET /api/ops/status/ — provider health, DB, redis, celery."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.conf import settings
        from agent_runtime.runner import LLMExecutor

        # LLM provider check
        provider = getattr(settings, 'LLM_PROVIDER', 'groq')
        executor = LLMExecutor(provider=provider)

        # Database check
        db_ok = False
        try:
            from django.db import connection
            connection.ensure_connection()
            db_ok = True
        except Exception:
            pass

        # Redis check
        redis_ok = False
        try:
            import redis
            r = redis.from_url(getattr(settings, 'CELERY_BROKER_URL', 'redis://localhost:6379/0'))
            r.ping()
            redis_ok = True
        except Exception:
            pass

        # Celery check
        celery_eager = getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False)

        # Email backend
        email_backend = getattr(settings, 'EMAIL_BACKEND', '')
        email_is_real = 'smtp' in email_backend.lower()

        # Groq key check (without exposing it)
        groq_key = getattr(settings, 'GROQ_API_KEY', '')
        has_groq = bool(groq_key)

        return Response({
            "llm": {
                "provider": provider,
                "model": executor.model,
                "ready": executor.is_ready,
                "error": executor._init_error if not executor.is_ready else None,
            },
            "database": {"ok": db_ok},
            "redis": {"ok": redis_ok},
            "celery": {"eager": celery_eager, "note": "sync mode" if celery_eager else "async with broker"},
            "email": {
                "backend": email_backend.split(".")[-1] if email_backend else "none",
                "is_real_smtp": email_is_real,
            },
            "api_keys": {
                "groq": has_groq,
                "openai": bool(os.environ.get('OPENAI_API_KEY', '')),
                "anthropic": bool(os.environ.get('ANTHROPIC_API_KEY', '')),
            },
        })
