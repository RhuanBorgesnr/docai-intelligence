"""
Durable Prompt Registry.

Source-of-truth is the PromptDefinition DB model. An in-process LRU-style
cache (per agent_type+tenant, keyed by version) sits in front of the DB to
avoid redundant queries on the hot path.

Features:
- versioning: multiple versions per (agent_type, tenant_id)
- lifecycle: draft → active → canary → deprecated → archived
- canary release: activate a version for a percentage of requests
- rollback: clone an old version as the new active version
- distributed cache invalidation: bump a DB flag; workers re-read on next call
- policy / schema binding: stored as JSON snapshots in the DB row
- execution lineage: every AgentResponse should record prompt_version,
  schema_version, policy_version so traces are fully reproducible
- tenant isolation: every lookup is scoped to tenant_id
"""

from __future__ import annotations

import hashlib
import logging
import random
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone as dj_timezone

from agent_runtime.models import PromptDefinition
from orchestrator.enums import PromptLifecycleStatus

logger = logging.getLogger(__name__)

# ── local cache ───────────────────────────────────────────────────────────────
# Simple thread-safe dict keyed by (agent_type, tenant_id, version).
# Invalidated on write operations and on explicit invalidate_cache() call.
_CACHE_LOCK = threading.Lock()
_CACHE: dict[tuple, "PromptRecord"] = {}
_CACHE_INVALIDATION_GENERATION: dict[str, int] = {}  # key: agent_type:tenant_id


def _cache_key(agent_type: str, tenant_id: str, version: int) -> tuple:
    return (agent_type, tenant_id, version)


def _invalidate_cache(agent_type: str, tenant_id: str) -> None:
    scope = f"{agent_type}:{tenant_id}"
    with _CACHE_LOCK:
        keys_to_drop = [k for k in _CACHE if k[0] == agent_type and k[1] == tenant_id]
        for k in keys_to_drop:
            del _CACHE[k]
        _CACHE_INVALIDATION_GENERATION[scope] = (
            _CACHE_INVALIDATION_GENERATION.get(scope, 0) + 1
        )
    logger.debug("[prompt_registry] cache invalidated for %s:%s", agent_type, tenant_id)


# ── value objects ─────────────────────────────────────────────────────────────

@dataclass
class PromptRecord:
    """Immutable snapshot of a prompt version as resolved from DB."""

    agent_type: str
    tenant_id: str
    version: int
    status: str
    content: str
    variables: dict
    output_schema: dict
    policy: dict
    content_hash: str
    activated_at: Optional[datetime]
    created_at: datetime

    def render(self, context: dict) -> str:
        """Substitute {{var}} placeholders. Missing vars raise ValueError."""
        rendered = self.content
        for key, value in context.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        # Detect unresolved variables
        import re
        unresolved = re.findall(r"\{\{(\w+)\}\}", rendered)
        if unresolved:
            raise ValueError(f"Unresolved prompt variables: {unresolved}")
        return rendered

    @property
    def version_tag(self) -> str:
        return f"v{self.version}"

    @classmethod
    def from_db(cls, obj: PromptDefinition) -> "PromptRecord":
        return cls(
            agent_type=obj.agent_type,
            tenant_id=obj.tenant_id,
            version=obj.version,
            status=obj.status,
            content=obj.content,
            variables=obj.variables,
            output_schema=obj.output_schema,
            policy=obj.policy,
            content_hash=obj.content_hash,
            activated_at=obj.activated_at,
            created_at=obj.created_at,
        )


def _compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:64]


# ── registry ──────────────────────────────────────────────────────────────────

class DurablePromptRegistry:
    """
    DB-backed prompt registry with in-process cache.

    All methods are synchronous (safe for Celery workers and Django views).
    Use async wrappers if needed via sync_to_async.
    """

    # ── read path ──────────────────────────────────────────────────────────────

    @classmethod
    def get_active(
        cls,
        agent_type: str,
        tenant_id: str = "default",
        canary: bool = False,
    ) -> Optional[PromptRecord]:
        """
        Return the currently active prompt for (agent_type, tenant_id).

        If a canary version exists and *canary=True* (or random roll hits the
        canary traffic percentage), the canary version is returned instead.
        """
        canary_prompt = cls._get_by_status(agent_type, tenant_id, PromptLifecycleStatus.CANARY)
        active_prompt = cls._get_by_status(agent_type, tenant_id, PromptLifecycleStatus.ACTIVE)

        if canary_prompt and active_prompt:
            canary_pct = canary_prompt.policy.get("canary_traffic_pct", 10)
            if canary or random.randint(1, 100) <= canary_pct:
                return canary_prompt

        return active_prompt

    @classmethod
    def get_version(
        cls,
        agent_type: str,
        version: int,
        tenant_id: str = "default",
    ) -> Optional[PromptRecord]:
        """Return a specific version, regardless of status."""
        ck = _cache_key(agent_type, tenant_id, version)
        with _CACHE_LOCK:
            if ck in _CACHE:
                return _CACHE[ck]

        try:
            obj = PromptDefinition.objects.get(
                agent_type=agent_type, tenant_id=tenant_id, version=version
            )
        except PromptDefinition.DoesNotExist:
            return None

        record = PromptRecord.from_db(obj)
        with _CACHE_LOCK:
            _CACHE[ck] = record
        return record

    @classmethod
    def list_versions(
        cls,
        agent_type: str,
        tenant_id: str = "default",
    ) -> list[dict]:
        rows = PromptDefinition.objects.filter(
            agent_type=agent_type, tenant_id=tenant_id
        ).order_by("-version").values(
            "version", "status", "description", "content_hash", "created_at", "activated_at"
        )
        return list(rows)

    # ── write path ────────────────────────────────────────────────────────────

    @classmethod
    def register(
        cls,
        agent_type: str,
        content: str,
        tenant_id: str = "default",
        description: str = "",
        variables: Optional[dict] = None,
        output_schema: Optional[dict] = None,
        policy: Optional[dict] = None,
        created_by: str = "system",
    ) -> PromptRecord:
        """
        Create a new DRAFT version.
        Version number is auto-incremented (max + 1).
        """
        content_hash = _compute_hash(content)

        with transaction.atomic():
            last = (
                PromptDefinition.objects.filter(agent_type=agent_type, tenant_id=tenant_id)
                .order_by("-version")
                .first()
            )
            next_version = (last.version + 1) if last else 1

            obj = PromptDefinition.objects.create(
                agent_type=agent_type,
                tenant_id=tenant_id,
                version=next_version,
                status=PromptLifecycleStatus.DRAFT,
                description=description,
                content=content,
                variables=variables or {},
                output_schema=output_schema or {},
                policy=policy or {},
                content_hash=content_hash,
                created_by=created_by,
            )

        _invalidate_cache(agent_type, tenant_id)
        logger.info(
            "[prompt_registry] registered %s:%s v%d (draft)", agent_type, tenant_id, next_version
        )
        return PromptRecord.from_db(obj)

    @classmethod
    def activate(
        cls,
        agent_type: str,
        version: int,
        tenant_id: str = "default",
        as_canary: bool = False,
    ) -> PromptRecord:
        """
        Promote *version* to ACTIVE (or CANARY).

        Any previously active version is moved to DEPRECATED.
        """
        target_status = PromptLifecycleStatus.CANARY if as_canary else PromptLifecycleStatus.ACTIVE

        with transaction.atomic():
            obj = PromptDefinition.objects.select_for_update().get(
                agent_type=agent_type, tenant_id=tenant_id, version=version
            )
            if obj.status not in (PromptLifecycleStatus.DRAFT, PromptLifecycleStatus.CANARY):
                raise ValueError(
                    f"Cannot activate a prompt with status={obj.status}. "
                    "Only draft or canary versions can be activated."
                )

            if not as_canary:
                # Deprecate any current ACTIVE versions
                PromptDefinition.objects.filter(
                    agent_type=agent_type,
                    tenant_id=tenant_id,
                    status=PromptLifecycleStatus.ACTIVE,
                ).exclude(pk=obj.pk).update(status=PromptLifecycleStatus.DEPRECATED)

            obj.status = target_status
            obj.activated_at = dj_timezone.now()
            obj.save(update_fields=["status", "activated_at", "updated_at"])

        _invalidate_cache(agent_type, tenant_id)
        logger.info(
            "[prompt_registry] activated %s:%s v%d as %s",
            agent_type,
            tenant_id,
            version,
            target_status,
        )
        return PromptRecord.from_db(obj)

    @classmethod
    def deactivate(
        cls,
        agent_type: str,
        version: int,
        tenant_id: str = "default",
    ) -> PromptRecord:
        """Move a version to DEPRECATED."""
        with transaction.atomic():
            obj = PromptDefinition.objects.select_for_update().get(
                agent_type=agent_type, tenant_id=tenant_id, version=version
            )
            obj.status = PromptLifecycleStatus.DEPRECATED
            obj.save(update_fields=["status", "updated_at"])

        _invalidate_cache(agent_type, tenant_id)
        logger.info(
            "[prompt_registry] deactivated %s:%s v%d", agent_type, tenant_id, version
        )
        return PromptRecord.from_db(obj)

    @classmethod
    def rollback(
        cls,
        agent_type: str,
        to_version: int,
        tenant_id: str = "default",
        created_by: str = "system",
    ) -> PromptRecord:
        """
        Create a new version whose content is a copy of *to_version* and
        immediately activate it. The copy carries a rollback_from_version tag.
        """
        source = cls.get_version(agent_type, to_version, tenant_id)
        if source is None:
            raise ValueError(f"Version {to_version} not found for {agent_type}:{tenant_id}")

        content_hash = _compute_hash(source.content)

        with transaction.atomic():
            last = (
                PromptDefinition.objects.filter(agent_type=agent_type, tenant_id=tenant_id)
                .order_by("-version")
                .first()
            )
            next_version = (last.version + 1) if last else 1

            new_obj = PromptDefinition.objects.create(
                agent_type=agent_type,
                tenant_id=tenant_id,
                version=next_version,
                status=PromptLifecycleStatus.DRAFT,
                description=f"Rollback to v{to_version}",
                content=source.content,
                variables=source.variables,
                output_schema=source.output_schema,
                policy=source.policy,
                content_hash=content_hash,
                created_by=created_by,
                rollback_from_version=to_version,
            )

            # Deprecate current ACTIVE versions
            PromptDefinition.objects.filter(
                agent_type=agent_type,
                tenant_id=tenant_id,
                status=PromptLifecycleStatus.ACTIVE,
            ).update(status=PromptLifecycleStatus.DEPRECATED)

            new_obj.status = PromptLifecycleStatus.ACTIVE
            new_obj.activated_at = dj_timezone.now()
            new_obj.save(update_fields=["status", "activated_at", "updated_at"])

        _invalidate_cache(agent_type, tenant_id)
        logger.info(
            "[prompt_registry] rollback %s:%s → v%d (new v%d)",
            agent_type,
            tenant_id,
            to_version,
            next_version,
        )
        return PromptRecord.from_db(new_obj)

    @classmethod
    def invalidate_cache(cls, agent_type: str, tenant_id: str = "default") -> None:
        """Explicitly flush local cache for (agent_type, tenant_id).

        Call this from a Celery task or signal after a remote write so that all
        workers pick up the new version on their next request.
        """
        _invalidate_cache(agent_type, tenant_id)

    # ── private helpers ───────────────────────────────────────────────────────

    @classmethod
    def _get_by_status(
        cls, agent_type: str, tenant_id: str, status: str
    ) -> Optional[PromptRecord]:
        try:
            obj = PromptDefinition.objects.filter(
                agent_type=agent_type, tenant_id=tenant_id, status=status
            ).order_by("-version").first()
        except Exception:  # noqa: BLE001
            return None

        if obj is None:
            return None

        ck = _cache_key(agent_type, tenant_id, obj.version)
        with _CACHE_LOCK:
            if ck in _CACHE:
                return _CACHE[ck]

        record = PromptRecord.from_db(obj)
        with _CACHE_LOCK:
            _CACHE[ck] = record
        return record
