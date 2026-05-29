"""
WebSocket broadcast utilities — integrates with existing event system.

Call these functions from services, tasks, or signals to push real-time
updates to connected WebSocket clients via the Redis channel layer.

Usage:
    from orchestrator.ws_broadcasts import broadcast_case_event
    await broadcast_case_event(case_id, event_type, payload)

For sync contexts (views, Celery tasks):
    from orchestrator.ws_broadcasts import sync_broadcast_case_event
    sync_broadcast_case_event(case_id, event_type, payload)
"""
from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

# Group name constants (must match consumers.py)
DASHBOARD_GROUP = "ws_dashboard"
EVENTS_GROUP = "ws_events"
AGENTS_GROUP = "ws_agents"


def _notifications_group(user_id: int) -> str:
    return f"ws_notifications_{user_id}"


# ── Async broadcast functions ─────────────────────────────────────────────────

async def broadcast_dashboard_update(payload: dict[str, Any]) -> None:
    """Push dashboard metrics update to all connected dashboard clients."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    await channel_layer.group_send(
        DASHBOARD_GROUP,
        {"type": "dashboard.update", "payload": {"type": "dashboard.update", "data": payload}},
    )


async def broadcast_case_event(
    case_id: int | str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Push a case event to the real-time events stream."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    message = {
        "type": "case.event",
        "payload": {
            "type": "case.event",
            "case_id": str(case_id),
            "event_type": event_type,
            "data": payload or {},
        },
    }
    await channel_layer.group_send(EVENTS_GROUP, message)


async def broadcast_agent_status(
    agent_name: str,
    status: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Push agent status update (heartbeat, task progress, etc.)."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    message = {
        "type": "agent.status",
        "payload": {
            "type": "agent.status",
            "agent": agent_name,
            "status": status,
            "detail": detail or {},
        },
    }
    await channel_layer.group_send(AGENTS_GROUP, message)


async def broadcast_notification(user_id: int, payload: dict[str, Any]) -> None:
    """Push a notification to a specific user's WebSocket connection."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    message = {
        "type": "notification",
        "payload": {"type": "notification", **payload},
    }
    await channel_layer.group_send(_notifications_group(user_id), message)


# ── Sync wrappers (for views, Celery tasks, signals) ─────────────────────────

def sync_broadcast_dashboard_update(payload: dict[str, Any]) -> None:
    """Sync wrapper for broadcast_dashboard_update."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            DASHBOARD_GROUP,
            {"type": "dashboard.update", "payload": {"type": "dashboard.update", "data": payload}},
        )
    except Exception as e:
        logger.warning("Failed to broadcast dashboard update: %s", e)


def sync_broadcast_case_event(
    case_id: int | str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Sync wrapper for broadcast_case_event."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        message = {
            "type": "case.event",
            "payload": {
                "type": "case.event",
                "case_id": str(case_id),
                "event_type": event_type,
                "data": payload or {},
            },
        }
        async_to_sync(channel_layer.group_send)(EVENTS_GROUP, message)
    except Exception as e:
        logger.warning("Failed to broadcast case event: %s", e)


def sync_broadcast_agent_status(
    agent_name: str,
    status: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Sync wrapper for broadcast_agent_status."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        message = {
            "type": "agent.status",
            "payload": {
                "type": "agent.status",
                "agent": agent_name,
                "status": status,
                "detail": detail or {},
            },
        }
        async_to_sync(channel_layer.group_send)(AGENTS_GROUP, message)
    except Exception as e:
        logger.warning("Failed to broadcast agent status: %s", e)


def sync_broadcast_notification(user_id: int, payload: dict[str, Any]) -> None:
    """Sync wrapper for broadcast_notification."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        message = {
            "type": "notification",
            "payload": {"type": "notification", **payload},
        }
        async_to_sync(channel_layer.group_send)(_notifications_group(user_id), message)
    except Exception as e:
        logger.warning("Failed to broadcast notification: %s", e)


def sync_broadcast_document_status(
    company_id: int,
    document_id: int,
    status: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """
    Broadcast document processing status to all connected clients of a company.

    Status values: uploaded, extracting_text, chunking, embedding, analyzing_financial,
                   analyzing_clauses, extracting_metadata, completed, failed
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        group_name = f"ws_documents_{company_id}"
        message = {
            "type": "document.status",
            "payload": {
                "type": "document.status",
                "document_id": document_id,
                "status": status,
                "detail": detail or {},
            },
        }
        async_to_sync(channel_layer.group_send)(group_name, message)
    except Exception as e:
        logger.warning("Failed to broadcast document status: %s", e)


# ── Dashboard snapshot (called by consumer on request_snapshot) ───────────────

async def get_dashboard_snapshot() -> dict[str, Any]:
    """Fetch current dashboard state for newly connected clients."""
    from channels.db import database_sync_to_async

    @database_sync_to_async
    def _fetch():
        try:
            from orchestrator.dashboard import get_operational_summary
            return get_operational_summary()
        except Exception as e:
            logger.warning("Failed to get dashboard snapshot: %s", e)
            return {"error": str(e)}

    return await _fetch()
