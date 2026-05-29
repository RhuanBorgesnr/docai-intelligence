"""
WebSocket Consumers for real-time operational updates.

Channels:
- DashboardConsumer: broadcasts dashboard metrics (pipeline, agents, system health)
- EventsConsumer: broadcasts case events and state transitions
- AgentStatusConsumer: broadcasts agent heartbeat and task progress
- NotificationsConsumer: per-user notification delivery
- DocumentStatusConsumer: per-company document processing updates (client-facing)

All consumers use Redis channel layer groups for pub/sub.
"""
from __future__ import annotations

import json
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)

# ── Group Names ───────────────────────────────────────────────────────────────
DASHBOARD_GROUP = "ws_dashboard"
EVENTS_GROUP = "ws_events"
AGENTS_GROUP = "ws_agents"


def _user_notifications_group(user_id: int) -> str:
    return f"ws_notifications_{user_id}"


def _company_documents_group(company_id: int) -> str:
    return f"ws_documents_{company_id}"


# ── Dashboard Consumer ────────────────────────────────────────────────────────

class DashboardConsumer(AsyncJsonWebsocketConsumer):
    """
    Broadcasts operational dashboard updates: pipeline stats, throughput,
    system health, approval summary.

    Group: ws_dashboard
    """

    async def connect(self):
        await self.channel_layer.group_add(DASHBOARD_GROUP, self.channel_name)
        await self.accept()
        logger.info("WS Dashboard connected: %s", self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(DASHBOARD_GROUP, self.channel_name)

    async def dashboard_update(self, event):
        """Handle dashboard.update messages from channel layer."""
        await self.send_json(event["payload"])

    async def receive_json(self, content, **kwargs):
        # Clients can request an immediate snapshot
        msg_type = content.get("type")
        if msg_type == "request_snapshot":
            from orchestrator.ws_broadcasts import get_dashboard_snapshot
            snapshot = await get_dashboard_snapshot()
            await self.send_json({"type": "dashboard.snapshot", "data": snapshot})


# ── Events Consumer ───────────────────────────────────────────────────────────

class EventsConsumer(AsyncJsonWebsocketConsumer):
    """
    Broadcasts case events in real-time: new events, state transitions,
    agent actions. Supports optional tenant filtering.

    Group: ws_events
    """

    async def connect(self):
        await self.channel_layer.group_add(EVENTS_GROUP, self.channel_name)
        await self.accept()
        logger.info("WS Events connected: %s", self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(EVENTS_GROUP, self.channel_name)

    async def case_event(self, event):
        """Handle case.event messages from channel layer."""
        await self.send_json(event["payload"])

    async def receive_json(self, content, **kwargs):
        # Read-only stream; ignore client messages
        pass


# ── Agent Status Consumer ─────────────────────────────────────────────────────

class AgentStatusConsumer(AsyncJsonWebsocketConsumer):
    """
    Broadcasts agent heartbeat, task start/complete, and performance metrics.

    Group: ws_agents
    """

    async def connect(self):
        await self.channel_layer.group_add(AGENTS_GROUP, self.channel_name)
        await self.accept()
        logger.info("WS Agents connected: %s", self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(AGENTS_GROUP, self.channel_name)

    async def agent_status(self, event):
        """Handle agent.status messages from channel layer."""
        await self.send_json(event["payload"])

    async def receive_json(self, content, **kwargs):
        # Read-only stream
        pass


# ── Notifications Consumer ────────────────────────────────────────────────────

class NotificationsConsumer(AsyncJsonWebsocketConsumer):
    """
    Per-user notification delivery via WebSocket.
    Requires authenticated connection (JWT token in query string).

    Group: ws_notifications_{user_id}
    """

    async def connect(self):
        user = self.scope.get("user")
        if isinstance(user, AnonymousUser) or not user:
            await self.close(code=4001)
            return

        self.group_name = _user_notifications_group(user.id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info("WS Notifications connected: user=%s", user.id)

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification(self, event):
        """Handle notification messages from channel layer."""
        await self.send_json(event["payload"])

    async def receive_json(self, content, **kwargs):
        # Clients can acknowledge notifications
        msg_type = content.get("type")
        if msg_type == "ack":
            notification_id = content.get("notification_id")
            if notification_id:
                logger.info("Notification acked: %s", notification_id)


# ── Document Status Consumer (Client-Facing) ─────────────────────────────────

class DocumentStatusConsumer(AsyncJsonWebsocketConsumer):
    """
    Per-company document processing status updates.
    Pushes real-time progress: uploaded → extracting → chunking → embedding → analyzing → done.

    Requires authenticated connection (JWT token in query string).
    Group: ws_documents_{company_id}
    """

    async def connect(self):
        user = self.scope.get("user")
        if isinstance(user, AnonymousUser) or not user:
            await self.close(code=4001)
            return

        # Get company from user profile
        from channels.db import database_sync_to_async

        @database_sync_to_async
        def get_company_id():
            try:
                return user.userprofile.company_id
            except Exception:
                return None

        company_id = await get_company_id()
        if not company_id:
            await self.close(code=4003)
            return

        self.group_name = _company_documents_group(company_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info("WS Documents connected: user=%s company=%s", user.id, company_id)

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def document_status(self, event):
        """Handle document.status messages — processing progress."""
        await self.send_json(event["payload"])

    async def receive_json(self, content, **kwargs):
        # Read-only stream
        pass
