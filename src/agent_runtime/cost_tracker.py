"""
Cost Tracker + Execution Log — operational observability for the digital team.

Tracks every LLM execution with:
- Tokens in/out, estimated cost
- Latency, retries, cache hits
- Agent type, prompt version
- Quality feedback (after human review)

Enables:
- Cost per lead calculation
- Cost per workflow
- Agent performance comparison
- Token budget monitoring
- Agent behavior refinement

Sprint 4 / Operational Phase.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.db import models
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from agent_runtime.prompt_registry import AgentType

logger = logging.getLogger(__name__)


# ── Cost rates (USD per 1K tokens) ───────────────────────────────────────────
# Update these when provider pricing changes
COST_RATES = {
    "openai": {"prompt": 0.0015, "completion": 0.002},       # gpt-3.5-turbo
    "openai_gpt4": {"prompt": 0.03, "completion": 0.06},     # gpt-4
    "openai_gpt4o": {"prompt": 0.005, "completion": 0.015},  # gpt-4o
    "anthropic": {"prompt": 0.003, "completion": 0.015},     # claude-3-haiku
    "anthropic_opus": {"prompt": 0.015, "completion": 0.075},# claude-3-opus
    "local": {"prompt": 0.0, "completion": 0.0},             # local/mock
    "groq": {"prompt": 0.0003, "completion": 0.0003},        # groq llama
}


class AgentExecution(models.Model):
    """
    Log of every agent execution — the source of truth for costs,
    performance, and refinement.
    """
    # Identity
    execution_id = models.CharField(max_length=128, unique=True)
    agent_type = models.CharField(max_length=50, db_index=True)
    prompt_version = models.IntegerField(default=1)
    provider = models.CharField(max_length=50, default="local")
    model_name = models.CharField(max_length=100, default="", blank=True)

    # Context
    tenant_id = models.CharField(max_length=100, default="docai_internal", db_index=True)
    correlation_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    lead_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    trigger = models.CharField(max_length=100, blank=True, default="")  # "routine", "manual", "webhook", "approval"

    # Tokens & Cost
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    estimated_cost_usd = models.FloatField(default=0.0)

    # Performance
    latency_ms = models.FloatField(default=0.0)
    llm_latency_ms = models.FloatField(default=0.0)
    retry_count = models.IntegerField(default=0)
    cache_hit = models.BooleanField(default=False)

    # Result
    status = models.CharField(max_length=30, default="success")  # success, failed, timeout, fallback
    output_summary = models.TextField(blank=True, default="")  # Short summary of what was produced
    error_message = models.TextField(blank=True, default="")

    # Feedback (for refinement)
    feedback_quality = models.IntegerField(null=True, blank=True, help_text="1-5 quality rating")
    feedback_useful = models.BooleanField(null=True, blank=True, help_text="Was the output useful?")
    feedback_notes = models.TextField(blank=True, default="")
    feedback_by = models.CharField(max_length=100, blank=True, default="")
    feedback_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["agent_type", "created_at"]),
            models.Index(fields=["tenant_id", "created_at"]),
            models.Index(fields=["lead_id"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.agent_type} {self.execution_id[:16]} — {self.status} ({self.total_tokens} tokens)"


# ── Recording ─────────────────────────────────────────────────────────────────

def record_execution(
    execution_id: str,
    agent_type: str,
    provider: str = "local",
    model_name: str = "",
    prompt_version: int = 1,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: float = 0.0,
    llm_latency_ms: float = 0.0,
    retry_count: int = 0,
    cache_hit: bool = False,
    status: str = "success",
    output_summary: str = "",
    error_message: str = "",
    lead_id: str = "",
    correlation_id: str = "",
    trigger: str = "",
    tenant_id: str = "docai_internal",
) -> AgentExecution:
    """
    Record an agent execution with cost estimation.
    Call this after every LLM invocation.
    """
    total_tokens = prompt_tokens + completion_tokens
    cost = estimate_cost(provider, prompt_tokens, completion_tokens)

    record = AgentExecution.objects.create(
        execution_id=execution_id,
        agent_type=agent_type,
        provider=provider,
        model_name=model_name,
        prompt_version=prompt_version,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
        latency_ms=latency_ms,
        llm_latency_ms=llm_latency_ms,
        retry_count=retry_count,
        cache_hit=cache_hit,
        status=status,
        output_summary=output_summary[:500],
        error_message=error_message[:500],
        lead_id=lead_id,
        correlation_id=correlation_id,
        trigger=trigger,
        tenant_id=tenant_id,
    )

    logger.info(
        "[COST] %s exec=%s tokens=%d cost=$%.4f latency=%dms",
        agent_type, execution_id[:12], total_tokens, cost, latency_ms,
    )
    return record


def estimate_cost(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost based on provider rates."""
    rates = COST_RATES.get(provider, COST_RATES["local"])
    return (
        (prompt_tokens / 1000) * rates["prompt"]
        + (completion_tokens / 1000) * rates["completion"]
    )


def record_feedback(
    execution_id: str,
    quality: int | None = None,
    useful: bool | None = None,
    notes: str = "",
    by: str = "",
) -> bool:
    """Record human feedback on an agent execution (for refinement)."""
    try:
        record = AgentExecution.objects.get(execution_id=execution_id)
        if quality is not None:
            record.feedback_quality = max(1, min(5, quality))
        if useful is not None:
            record.feedback_useful = useful
        if notes:
            record.feedback_notes = notes
        if by:
            record.feedback_by = by
        record.feedback_at = timezone.now()
        record.save(update_fields=[
            "feedback_quality", "feedback_useful", "feedback_notes",
            "feedback_by", "feedback_at",
        ])
        return True
    except AgentExecution.DoesNotExist:
        return False


# ── Cost Analytics ────────────────────────────────────────────────────────────

def cost_summary(tenant_id: str = "docai_internal", days: int = 7) -> dict[str, Any]:
    """
    Cost summary for the ops dashboard.
    Returns totals and per-agent breakdown.
    """
    since = timezone.now() - timedelta(days=days)
    qs = AgentExecution.objects.filter(tenant_id=tenant_id, created_at__gte=since)

    totals = qs.aggregate(
        total_cost=Sum("estimated_cost_usd"),
        total_tokens=Sum("total_tokens"),
        total_executions=Count("id"),
        avg_latency=Avg("latency_ms"),
    )

    per_agent = list(
        qs.values("agent_type").annotate(
            cost=Sum("estimated_cost_usd"),
            tokens=Sum("total_tokens"),
            executions=Count("id"),
            avg_latency=Avg("latency_ms"),
            avg_quality=Avg("feedback_quality"),
            failures=Count("id", filter=models.Q(status="failed")),
        ).order_by("-cost")
    )

    # Cost per lead
    leads_with_cost = (
        qs.exclude(lead_id="")
        .values("lead_id")
        .annotate(cost=Sum("estimated_cost_usd"), execs=Count("id"))
        .order_by("-cost")[:10]
    )

    return {
        "period_days": days,
        "total_cost_usd": round(totals["total_cost"] or 0, 4),
        "total_tokens": totals["total_tokens"] or 0,
        "total_executions": totals["total_executions"] or 0,
        "avg_latency_ms": round(totals["avg_latency"] or 0, 1),
        "per_agent": per_agent,
        "top_leads_by_cost": list(leads_with_cost),
    }


def agent_performance(agent_type: str, days: int = 7) -> dict[str, Any]:
    """
    Detailed performance metrics for a single agent (for refinement).
    """
    since = timezone.now() - timedelta(days=days)
    qs = AgentExecution.objects.filter(agent_type=agent_type, created_at__gte=since)

    totals = qs.aggregate(
        total_executions=Count("id"),
        successes=Count("id", filter=models.Q(status="success")),
        failures=Count("id", filter=models.Q(status="failed")),
        fallbacks=Count("id", filter=models.Q(status="fallback")),
        avg_latency=Avg("latency_ms"),
        avg_tokens=Avg("total_tokens"),
        avg_cost=Avg("estimated_cost_usd"),
        avg_quality=Avg("feedback_quality"),
        total_cost=Sum("estimated_cost_usd"),
    )

    recent = list(
        qs.order_by("-created_at")[:10].values(
            "execution_id", "status", "total_tokens", "estimated_cost_usd",
            "latency_ms", "output_summary", "feedback_quality", "created_at",
        )
    )

    return {
        "agent_type": agent_type,
        "period_days": days,
        **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in totals.items()},
        "success_rate": round(
            (totals["successes"] or 0) / max(totals["total_executions"] or 1, 1) * 100, 1
        ),
        "recent_executions": recent,
    }
