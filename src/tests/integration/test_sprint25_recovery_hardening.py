"""
Sprint 2.5 — recovery, replay, and concurrency hardening tests.

Covers:
- Notification idempotency / duplicate submission suppression
- Notification dead-lettering after max_retries
- Notification retry sweep picks up due records
- DurablePromptRegistry: register, activate, canary, rollback, cache invalidation
- CircuitBreaker: open on threshold, half-open probe, close on success
- RateLimiter: acquires tokens, rejects when over limit
- InFlightProtection: prevents duplicate concurrent processing
- EventOutbox replay safety: published entries not re-claimed
- EventInbox deduplicate across consumers
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone as dj_timezone

from agent_runtime.durable_prompt_registry import DurablePromptRegistry, _invalidate_cache
from agent_runtime.runtime_protection import (
    CircuitBreaker,
    CircuitBreakerState,
    InFlightProtection,
    RateLimiter,
)
from notifications.durable_service import DurableNotificationService
from notifications.models import Notification, NotificationDeliveryAttempt
from orchestrator.durable_events import (
    claim_pending_outbox_batch,
    mark_event_processed,
    mark_outbox_published,
    persist_case_event,
    persist_runtime_outbox_event,
)
from orchestrator.enums import DurableNotificationStatus, Priority, PromptLifecycleStatus
from orchestrator.models import Case, EventInbox, EventOutbox


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def case(db):
    return Case.objects.create(
        external_ref=f"case-recovery-{uuid.uuid4().hex[:8]}",
        tenant_id="tenant-recovery",
        title="Recovery Test Case",
        correlation_id=f"corr-{uuid.uuid4().hex[:8]}",
        trace_id=f"trace-{uuid.uuid4().hex[:8]}",
    )


# ── notification: idempotency ─────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_notification_submit_is_idempotent(case):
    nid = f"notif-idem-{uuid.uuid4().hex[:8]}"

    first = DurableNotificationService.submit_sync(
        notification_id=nid,
        case_id=case.external_ref,
        channel=Notification.Channel.LOG,
        recipient="ops@company.com",
        message="Hello",
        tenant_id=case.tenant_id,
        correlation_id=case.correlation_id,
    )
    second = DurableNotificationService.submit_sync(
        notification_id=nid,
        case_id=case.external_ref,
        channel=Notification.Channel.LOG,
        recipient="ops@company.com",
        message="Hello (duplicate)",
        tenant_id=case.tenant_id,
        correlation_id=case.correlation_id,
    )

    assert first.pk == second.pk
    assert Notification.objects.filter(notification_id=nid).count() == 1


# ── notification: dead-letter after max_retries ───────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_notification_dead_lettered_after_max_retries(case):
    nid = f"notif-dead-{uuid.uuid4().hex[:8]}"

    def always_fail(_notif):
        return False, {"error": "simulated_failure"}

    with patch(
        "notifications.durable_service._dispatch_channel",
        side_effect=lambda notif, channel: (False, {"error": "fail"}, 0.0),
    ):
        notif = DurableNotificationService.submit_sync(
            notification_id=nid,
            case_id=case.external_ref,
            channel=Notification.Channel.EMAIL,
            recipient="noreply@company.com",
            message="Dead-letter test",
            max_retries=1,
            tenant_id=case.tenant_id,
        )

        # One retry sweep to exhaust the single allowed attempt
        notif.next_attempt_at = dj_timezone.now() - timedelta(seconds=1)
        notif.status = DurableNotificationStatus.FAILED
        notif.save()

        DurableNotificationService.retry_pending_sync(limit=10)

    notif.refresh_from_db()
    assert notif.is_dead is True
    assert notif.status == DurableNotificationStatus.FAILED


# ── notification: retry sweep picks up due records ────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_notification_retry_sweep_delivers_due_record(case):
    nid = f"notif-retry-{uuid.uuid4().hex[:8]}"

    # Submit as pending/failed with past next_attempt_at so sweep picks it up
    from notifications.models import Notification as NM
    from orchestrator.durable_events import persist_runtime_outbox_event  # noqa: F401

    import hashlib as _hm
    idem = _hm.sha256(f"{nid}:{case.external_ref}".encode()).hexdigest()[:64]

    NM.objects.create(
        notification_id=nid,
        case=case,
        tenant_id=case.tenant_id,
        channel=NM.Channel.LOG,
        recipient="sweep@company.com",
        message="Sweep test",
        status=DurableNotificationStatus.FAILED,
        idempotency_key=idem,
        max_retries=3,
        attempts=1,
        next_attempt_at=dj_timezone.now() - timedelta(seconds=5),
    )

    results = DurableNotificationService.retry_pending_sync(limit=10)
    assert results["retried"] >= 1
    assert results["succeeded"] >= 1


# ── prompt registry: full lifecycle ──────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_prompt_registry_register_activate_rollback():
    agent_type = f"test_agent_{uuid.uuid4().hex[:6]}"
    tenant_id = "tenant-prompt"

    # Register two drafts
    v1 = DurablePromptRegistry.register(
        agent_type=agent_type,
        tenant_id=tenant_id,
        content="Hello {{name}}, you have {{count}} messages.",
        variables={"name": "str", "count": "int"},
        description="v1 prompt",
    )
    assert v1.version == 1
    assert v1.status == PromptLifecycleStatus.DRAFT

    v2 = DurablePromptRegistry.register(
        agent_type=agent_type,
        tenant_id=tenant_id,
        content="Hi {{name}}, you have {{count}} new messages!",
        variables={"name": "str", "count": "int"},
        description="v2 prompt",
    )
    assert v2.version == 2

    # Activate v1
    DurablePromptRegistry.activate(agent_type, version=1, tenant_id=tenant_id)
    active = DurablePromptRegistry.get_active(agent_type, tenant_id=tenant_id)
    assert active is not None
    assert active.version == 1

    # Activate v2 as canary
    DurablePromptRegistry.activate(agent_type, version=2, tenant_id=tenant_id, as_canary=True)
    canary = DurablePromptRegistry.get_active(agent_type, tenant_id=tenant_id, canary=True)
    assert canary is not None
    assert canary.version == 2

    # Rollback to v1 creates v3
    rolled = DurablePromptRegistry.rollback(agent_type, to_version=1, tenant_id=tenant_id)
    assert rolled.version == 3
    assert rolled.status == PromptLifecycleStatus.ACTIVE

    # Active is now v3 (content identical to v1)
    active_after = DurablePromptRegistry.get_active(agent_type, tenant_id=tenant_id)
    assert active_after.version == 3
    assert active_after.content == v1.content


@pytest.mark.django_db(transaction=True)
def test_prompt_registry_render_raises_on_missing_var():
    agent_type = f"test_agent_{uuid.uuid4().hex[:6]}"
    tenant_id = "tenant-render"

    rec = DurablePromptRegistry.register(
        agent_type=agent_type,
        tenant_id=tenant_id,
        content="Hello {{name}}, today is {{date}}.",
        variables={"name": "str", "date": "str"},
    )
    DurablePromptRegistry.activate(agent_type, version=rec.version, tenant_id=tenant_id)
    active = DurablePromptRegistry.get_active(agent_type, tenant_id=tenant_id)

    rendered = active.render({"name": "Alice", "date": "2026-05-12"})
    assert "Alice" in rendered

    with pytest.raises(ValueError, match="Unresolved prompt variables"):
        active.render({"name": "Alice"})  # missing 'date'


@pytest.mark.django_db(transaction=True)
def test_prompt_registry_cache_invalidation():
    agent_type = f"test_agent_{uuid.uuid4().hex[:6]}"
    tenant_id = "tenant-cache"

    rec = DurablePromptRegistry.register(
        agent_type=agent_type, tenant_id=tenant_id, content="Version one"
    )
    DurablePromptRegistry.activate(agent_type, version=rec.version, tenant_id=tenant_id)

    # Prime cache
    _ = DurablePromptRegistry.get_active(agent_type, tenant_id=tenant_id)

    # Simulate remote write that doesn't go through local registry
    from agent_runtime.models import PromptDefinition
    PromptDefinition.objects.filter(
        agent_type=agent_type, tenant_id=tenant_id, version=rec.version
    ).update(content="Version one — updated remotely")

    # Without invalidation, cache returns stale
    cached = DurablePromptRegistry.get_version(agent_type, rec.version, tenant_id=tenant_id)
    assert cached.content == "Version one"  # stale

    # After invalidation, fresh read
    DurablePromptRegistry.invalidate_cache(agent_type, tenant_id=tenant_id)
    fresh = DurablePromptRegistry.get_version(agent_type, rec.version, tenant_id=tenant_id)
    assert "updated remotely" in fresh.content


# ── circuit breaker ───────────────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_circuit_breaker_opens_on_threshold():
    key = f"cb-test-{uuid.uuid4().hex[:8]}"
    cb = CircuitBreaker(key, failure_threshold=3, reset_timeout_seconds=999)

    assert cb.allow_request() is True
    cb.record_failure()
    cb.record_failure()
    assert cb.allow_request() is True  # still under threshold
    cb.record_failure()  # hits threshold
    assert cb.allow_request() is False


@pytest.mark.django_db(transaction=True)
def test_circuit_breaker_half_open_probe_and_close():
    key = f"cb-test-{uuid.uuid4().hex[:8]}"
    cb = CircuitBreaker(key, failure_threshold=2, success_threshold=1, reset_timeout_seconds=1)

    cb.record_failure()
    cb.record_failure()
    assert cb.allow_request() is False  # open

    # After reset_timeout_seconds=1, wait for timeout to elapse
    import time
    time.sleep(1.1)
    assert cb.allow_request() is True   # half-open probe

    cb.record_success()
    assert cb.allow_request() is True   # closed again


# ── rate limiter ──────────────────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_rate_limiter_blocks_over_capacity():
    key = f"rl-test-{uuid.uuid4().hex[:8]}"
    limiter = RateLimiter(key, capacity=3, window_seconds=60)

    assert limiter.acquire() is True
    assert limiter.acquire() is True
    assert limiter.acquire() is True
    assert limiter.acquire() is False  # capacity exhausted
    assert limiter.remaining() == 0


# ── inflight protection ───────────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_inflight_prevents_duplicate_concurrent_lease():
    key = f"if-test-{uuid.uuid4().hex[:8]}"
    guard = InFlightProtection(key)

    assert guard.acquire("item-1", lease_seconds=60) is True
    assert guard.acquire("item-1", lease_seconds=60) is False  # already held

    guard.release("item-1")
    assert guard.acquire("item-1", lease_seconds=60) is True  # released, acquirable again


@pytest.mark.django_db(transaction=True)
def test_inflight_max_concurrent_limit():
    key = f"if-test-{uuid.uuid4().hex[:8]}"
    guard = InFlightProtection(key, max_concurrent=2)

    assert guard.acquire("item-1", lease_seconds=60) is True
    assert guard.acquire("item-2", lease_seconds=60) is True
    assert guard.acquire("item-3", lease_seconds=60) is False  # max reached


# ── outbox replay safety ──────────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_outbox_published_events_not_re_claimed(case):
    # Create two outbox events; mark first as published
    outbox1 = persist_runtime_outbox_event(
        event_id=f"replay-{uuid.uuid4().hex}",
        case=case,
        event_type="test.replay.1",
        source="test",
        tenant_id=case.tenant_id,
        correlation_id=case.correlation_id,
        trace_id=case.trace_id,
        payload={"idx": 1},
    )
    outbox2 = persist_runtime_outbox_event(
        event_id=f"replay-{uuid.uuid4().hex}",
        case=case,
        event_type="test.replay.2",
        source="test",
        tenant_id=case.tenant_id,
        correlation_id=case.correlation_id,
        trace_id=case.trace_id,
        payload={"idx": 2},
    )

    mark_outbox_published(outbox1)

    batch = claim_pending_outbox_batch(limit=10)
    claimed_ids = [b.pk for b in batch]

    assert outbox1.pk not in claimed_ids
    assert outbox2.pk in claimed_ids


# ── inbox dedupe across consumers ────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_inbox_deduplicate_per_consumer(case):
    result = persist_case_event(
        case=case,
        event_id=f"evt-inbox-{uuid.uuid4().hex[:8]}",
        event_type="lead.received",
        event_version="1.0",
        source="test",
        priority=Priority.MEDIUM,
        occurred_at=dj_timezone.now(),
        correlation_id=case.correlation_id,
        trace_id=case.trace_id,
        tenant_id=case.tenant_id,
        payload={"x": 1},
        meta={},
    )

    assert mark_event_processed(consumer="worker-A", event=result.event) is True
    assert mark_event_processed(consumer="worker-A", event=result.event) is False
    assert mark_event_processed(consumer="worker-B", event=result.event) is True

    assert EventInbox.objects.filter(event_id=result.event.event_id).count() == 2
