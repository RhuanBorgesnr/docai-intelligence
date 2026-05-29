"""
Runtime protection primitives.

Provides:
1. CircuitBreaker — DB-backed per-resource circuit breaker.
2. RateLimiter    — DB-backed sliding-window rate limiter (token bucket via DB row).
3. InFlightCounter — DB-backed in-flight request counter with lease expiry.

All classes operate on Django models so state survives worker restarts and is
shared across multiple Celery/Django workers on the same PostgreSQL instance.

These are intentionally simple and do not require Redis (though Redis could be
swapped in as a faster backend if desired).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.db import models, transaction
from django.utils import timezone as dj_timezone

logger = logging.getLogger(__name__)


# ── models ────────────────────────────────────────────────────────────────────

class CircuitBreakerState(models.Model):
    """Persistent circuit breaker state per resource key."""

    class CircuitStatus(models.TextChoices):
        CLOSED = "closed", "Closed"   # healthy
        OPEN = "open", "Open"          # failing, blocking calls
        HALF_OPEN = "half_open", "Half-Open"  # probing recovery

    resource_key = models.CharField(max_length=200, unique=True)
    status = models.CharField(
        max_length=20, choices=CircuitStatus.choices, default=CircuitStatus.CLOSED
    )
    failure_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failure_threshold = models.PositiveIntegerField(default=5)
    success_threshold = models.PositiveIntegerField(default=2)  # half-open → closed
    last_failure_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    reset_timeout_seconds = models.PositiveIntegerField(default=60)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "agent_runtime"

    def __str__(self) -> str:
        return f"CircuitBreaker[{self.resource_key}] status={self.status}"


class RateLimitBucket(models.Model):
    """Token-bucket rate limit state per (resource_key, window)."""

    resource_key = models.CharField(max_length=200)
    window_start = models.DateTimeField()
    window_seconds = models.PositiveIntegerField(default=60)
    capacity = models.PositiveIntegerField(default=100)
    tokens_used = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "agent_runtime"
        constraints = [
            models.UniqueConstraint(
                fields=["resource_key", "window_start"], name="uniq_rate_limit_bucket"
            )
        ]
        indexes = [
            models.Index(fields=["resource_key", "window_start"]),
        ]


class InFlightRecord(models.Model):
    """Track in-flight work items with lease expiry."""

    resource_key = models.CharField(max_length=200, db_index=True)
    item_id = models.CharField(max_length=200)
    leased_until = models.DateTimeField()
    worker_id = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "agent_runtime"
        constraints = [
            models.UniqueConstraint(fields=["resource_key", "item_id"], name="uniq_inflight")
        ]
        indexes = [
            models.Index(fields=["resource_key", "leased_until"]),
        ]


# ── circuit breaker ───────────────────────────────────────────────────────────

class CircuitBreaker:
    """
    DB-backed circuit breaker.

    Usage:
        cb = CircuitBreaker("llm:groq")
        if cb.allow_request():
            try:
                result = call_groq(...)
                cb.record_success()
            except Exception:
                cb.record_failure()
                raise
        else:
            raise RuntimeError("Circuit open for llm:groq")
    """

    def __init__(
        self,
        resource_key: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        reset_timeout_seconds: int = 60,
    ) -> None:
        self.resource_key = resource_key
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.reset_timeout_seconds = reset_timeout_seconds

    def _state(self) -> CircuitBreakerState:
        obj, _ = CircuitBreakerState.objects.get_or_create(
            resource_key=self.resource_key,
            defaults={
                "failure_threshold": self.failure_threshold,
                "success_threshold": self.success_threshold,
                "reset_timeout_seconds": self.reset_timeout_seconds,
            },
        )
        return obj

    def allow_request(self) -> bool:
        """Returns True if a request should be allowed through."""
        state = self._state()

        if state.status == CircuitBreakerState.CircuitStatus.CLOSED:
            return True

        if state.status == CircuitBreakerState.CircuitStatus.OPEN:
            # Check if reset timeout has elapsed → half-open
            if state.opened_at:
                age = (dj_timezone.now() - state.opened_at).total_seconds()
                if age >= state.reset_timeout_seconds:
                    with transaction.atomic():
                        CircuitBreakerState.objects.filter(pk=state.pk).update(
                            status=CircuitBreakerState.CircuitStatus.HALF_OPEN,
                            success_count=0,
                        )
                    logger.info(
                        "[circuit_breaker] %s → half-open (probe allowed)", self.resource_key
                    )
                    return True  # allow probe request
            return False

        # HALF_OPEN: allow one probe
        return True

    def record_success(self) -> None:
        with transaction.atomic():
            state, _ = CircuitBreakerState.objects.select_for_update().get_or_create(
                resource_key=self.resource_key,
                defaults={
                    "failure_threshold": self.failure_threshold,
                    "success_threshold": self.success_threshold,
                    "reset_timeout_seconds": self.reset_timeout_seconds,
                },
            )
            state.success_count += 1

            if state.status == CircuitBreakerState.CircuitStatus.HALF_OPEN:
                if state.success_count >= state.success_threshold:
                    state.status = CircuitBreakerState.CircuitStatus.CLOSED
                    state.failure_count = 0
                    logger.info(
                        "[circuit_breaker] %s → closed (recovered)", self.resource_key
                    )

            state.save(update_fields=["success_count", "status", "failure_count", "updated_at"])

    def record_failure(self) -> None:
        with transaction.atomic():
            state, _ = CircuitBreakerState.objects.select_for_update().get_or_create(
                resource_key=self.resource_key,
                defaults={
                    "failure_threshold": self.failure_threshold,
                    "success_threshold": self.success_threshold,
                    "reset_timeout_seconds": self.reset_timeout_seconds,
                },
            )
            state.failure_count += 1
            state.last_failure_at = dj_timezone.now()

            if (
                state.status != CircuitBreakerState.CircuitStatus.OPEN
                and state.failure_count >= state.failure_threshold
            ):
                state.status = CircuitBreakerState.CircuitStatus.OPEN
                state.opened_at = dj_timezone.now()
                logger.warning(
                    "[circuit_breaker] %s → OPEN (failure_count=%d)",
                    self.resource_key,
                    state.failure_count,
                )

            state.save(
                update_fields=[
                    "failure_count",
                    "last_failure_at",
                    "status",
                    "opened_at",
                    "updated_at",
                ]
            )

    def status(self) -> str:
        return self._state().status


# ── rate limiter ──────────────────────────────────────────────────────────────

class RateLimiter:
    """
    DB-backed sliding-window token-bucket rate limiter.

    Usage:
        limiter = RateLimiter("groq:tenant-a", capacity=10, window_seconds=60)
        if limiter.acquire():
            call_groq(...)
        else:
            raise RuntimeError("Rate limit exceeded for groq:tenant-a")
    """

    def __init__(
        self,
        resource_key: str,
        capacity: int = 100,
        window_seconds: int = 60,
    ) -> None:
        self.resource_key = resource_key
        self.capacity = capacity
        self.window_seconds = window_seconds

    def _window_start(self) -> "dj_timezone.datetime":
        now = dj_timezone.now()
        # Floor to nearest window boundary
        ts = int(now.timestamp())
        floored = ts - (ts % self.window_seconds)
        from datetime import datetime, timezone
        return datetime.fromtimestamp(floored, tz=timezone.utc)

    def acquire(self, tokens: int = 1) -> bool:
        """Attempt to consume *tokens*. Returns False if limit exceeded."""
        window = self._window_start()

        with transaction.atomic():
            bucket, created = RateLimitBucket.objects.select_for_update().get_or_create(
                resource_key=self.resource_key,
                window_start=window,
                defaults={
                    "window_seconds": self.window_seconds,
                    "capacity": self.capacity,
                    "tokens_used": 0,
                },
            )

            if bucket.tokens_used + tokens > self.capacity:
                return False

            bucket.tokens_used += tokens
            bucket.save(update_fields=["tokens_used", "updated_at"])
            return True

    def remaining(self) -> int:
        window = self._window_start()
        try:
            bucket = RateLimitBucket.objects.get(
                resource_key=self.resource_key, window_start=window
            )
            return max(0, self.capacity - bucket.tokens_used)
        except RateLimitBucket.DoesNotExist:
            return self.capacity


# ── inflight counter ──────────────────────────────────────────────────────────

class InFlightProtection:
    """
    Guard against processing the same item concurrently across workers.

    Usage:
        guard = InFlightProtection("agent:docai_operator")
        if guard.acquire("cmd-123", lease_seconds=30):
            try:
                process_command("cmd-123")
            finally:
                guard.release("cmd-123")
    """

    def __init__(self, resource_key: str, max_concurrent: Optional[int] = None) -> None:
        self.resource_key = resource_key
        self.max_concurrent = max_concurrent

    def acquire(self, item_id: str, lease_seconds: int = 30, worker_id: str = "") -> bool:
        """Returns True if the lease was acquired."""
        now = dj_timezone.now()

        # Clean up expired leases first
        InFlightRecord.objects.filter(
            resource_key=self.resource_key, leased_until__lt=now
        ).delete()

        if self.max_concurrent is not None:
            current = InFlightRecord.objects.filter(resource_key=self.resource_key).count()
            if current >= self.max_concurrent:
                return False

        try:
            with transaction.atomic():
                InFlightRecord.objects.create(
                    resource_key=self.resource_key,
                    item_id=item_id,
                    leased_until=now + timedelta(seconds=lease_seconds),
                    worker_id=worker_id,
                )
            return True
        except Exception:  # noqa: BLE001
            return False  # unique constraint violation → already acquired

    def release(self, item_id: str) -> None:
        InFlightRecord.objects.filter(
            resource_key=self.resource_key, item_id=item_id
        ).delete()

    def count(self) -> int:
        now = dj_timezone.now()
        return InFlightRecord.objects.filter(
            resource_key=self.resource_key, leased_until__gt=now
        ).count()
