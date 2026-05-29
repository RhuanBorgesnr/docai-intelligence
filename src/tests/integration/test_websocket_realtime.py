"""
Integration tests for WebSocket real-time system (Django Channels).

Tests cover:
- Consumer connection/disconnection
- Group message broadcasting
- JWT authentication for notifications
- Dashboard snapshot request
- Broadcast utility functions
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from django.test import TestCase, override_settings
from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from asgiref.sync import sync_to_async

from orchestrator.consumers import (
    DashboardConsumer,
    EventsConsumer,
    AgentStatusConsumer,
    NotificationsConsumer,
    DASHBOARD_GROUP,
    EVENTS_GROUP,
    AGENTS_GROUP,
)
from orchestrator.ws_broadcasts import (
    sync_broadcast_case_event,
    sync_broadcast_agent_status,
    sync_broadcast_dashboard_update,
    sync_broadcast_notification,
)


# Use in-memory channel layer for tests
TEST_CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}


@pytest.mark.asyncio
@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class TestDashboardConsumer:
    """Tests for DashboardConsumer WebSocket."""

    async def test_connect_and_disconnect(self):
        communicator = WebsocketCommunicator(DashboardConsumer.as_asgi(), "/ws/dashboard/")
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    async def test_receive_dashboard_update(self):
        communicator = WebsocketCommunicator(DashboardConsumer.as_asgi(), "/ws/dashboard/")
        connected, _ = await communicator.connect()
        assert connected

        # Send message to group
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            DASHBOARD_GROUP,
            {
                "type": "dashboard.update",
                "payload": {"type": "dashboard.update", "data": {"cases_total": 42}},
            },
        )

        response = await communicator.receive_json_from()
        assert response["type"] == "dashboard.update"
        assert response["data"]["cases_total"] == 42
        await communicator.disconnect()

    async def test_request_snapshot(self):
        communicator = WebsocketCommunicator(DashboardConsumer.as_asgi(), "/ws/dashboard/")
        connected, _ = await communicator.connect()
        assert connected

        with patch("orchestrator.ws_broadcasts.get_dashboard_snapshot", new_callable=AsyncMock) as mock_snap:
            mock_snap.return_value = {"cases_total": 10, "agents_active": 3}
            await communicator.send_json_to({"type": "request_snapshot"})
            response = await communicator.receive_json_from()
            assert response["type"] == "dashboard.snapshot"

        await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class TestEventsConsumer:
    """Tests for EventsConsumer WebSocket."""

    async def test_connect(self):
        communicator = WebsocketCommunicator(EventsConsumer.as_asgi(), "/ws/events/")
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    async def test_receive_case_event(self):
        communicator = WebsocketCommunicator(EventsConsumer.as_asgi(), "/ws/events/")
        connected, _ = await communicator.connect()
        assert connected

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            EVENTS_GROUP,
            {
                "type": "case.event",
                "payload": {
                    "type": "case.event",
                    "case_id": "123",
                    "event_type": "document.uploaded",
                    "data": {"filename": "balanco.pdf"},
                },
            },
        )

        response = await communicator.receive_json_from()
        assert response["type"] == "case.event"
        assert response["case_id"] == "123"
        assert response["event_type"] == "document.uploaded"
        await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class TestAgentStatusConsumer:
    """Tests for AgentStatusConsumer WebSocket."""

    async def test_connect(self):
        communicator = WebsocketCommunicator(AgentStatusConsumer.as_asgi(), "/ws/agents/")
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    async def test_receive_agent_status(self):
        communicator = WebsocketCommunicator(AgentStatusConsumer.as_asgi(), "/ws/agents/")
        connected, _ = await communicator.connect()
        assert connected

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            AGENTS_GROUP,
            {
                "type": "agent.status",
                "payload": {
                    "type": "agent.status",
                    "agent": "sdr",
                    "status": "task_complete",
                    "detail": {"execution_id": "exec-001", "latency_ms": 250},
                },
            },
        )

        response = await communicator.receive_json_from()
        assert response["type"] == "agent.status"
        assert response["agent"] == "sdr"
        assert response["status"] == "task_complete"
        await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class TestNotificationsConsumer:
    """Tests for NotificationsConsumer WebSocket (requires auth)."""

    async def test_reject_unauthenticated(self):
        communicator = WebsocketCommunicator(NotificationsConsumer.as_asgi(), "/ws/notifications/")
        # Simulate anonymous user scope
        communicator.scope["user"] = None
        connected, code = await communicator.connect()
        # Should reject with 4001
        assert not connected or code == 4001

    async def test_accept_authenticated(self):
        communicator = WebsocketCommunicator(NotificationsConsumer.as_asgi(), "/ws/notifications/")
        # Simulate authenticated user
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.__class__.__name__ = "User"
        communicator.scope["user"] = mock_user

        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    async def test_receive_notification(self):
        communicator = WebsocketCommunicator(NotificationsConsumer.as_asgi(), "/ws/notifications/")
        mock_user = MagicMock()
        mock_user.id = 42
        communicator.scope["user"] = mock_user

        connected, _ = await communicator.connect()
        assert connected

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"ws_notifications_42",
            {
                "type": "notification",
                "payload": {
                    "type": "notification",
                    "title": "Lead quente!",
                    "body": "Novo lead ICP score 95",
                    "notification_id": "notif-001",
                },
            },
        )

        response = await communicator.receive_json_from()
        assert response["type"] == "notification"
        assert response["title"] == "Lead quente!"
        await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class TestBroadcastUtilities(TestCase):
    """Tests for sync broadcast utility functions."""

    def test_sync_broadcast_case_event(self):
        """sync_broadcast_case_event should not raise even without active consumers."""
        # Should be no-op when no consumers connected
        sync_broadcast_case_event(
            case_id=1,
            event_type="test.event",
            payload={"key": "value"},
        )

    def test_sync_broadcast_agent_status(self):
        """sync_broadcast_agent_status should not raise."""
        sync_broadcast_agent_status(
            agent_name="sdr",
            status="heartbeat",
            detail={"uptime": 3600},
        )

    def test_sync_broadcast_dashboard_update(self):
        """sync_broadcast_dashboard_update should not raise."""
        sync_broadcast_dashboard_update({"cases_total": 10})

    def test_sync_broadcast_notification(self):
        """sync_broadcast_notification should not raise."""
        sync_broadcast_notification(
            user_id=1,
            payload={"title": "Test", "body": "Hello"},
        )


@pytest.mark.asyncio
@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class TestMultipleConsumersReceive:
    """Test that multiple consumers on the same group all receive messages."""

    async def test_multiple_dashboard_clients(self):
        comm1 = WebsocketCommunicator(DashboardConsumer.as_asgi(), "/ws/dashboard/")
        comm2 = WebsocketCommunicator(DashboardConsumer.as_asgi(), "/ws/dashboard/")

        connected1, _ = await comm1.connect()
        connected2, _ = await comm2.connect()
        assert connected1 and connected2

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            DASHBOARD_GROUP,
            {
                "type": "dashboard.update",
                "payload": {"type": "dashboard.update", "data": {"ping": True}},
            },
        )

        resp1 = await comm1.receive_json_from()
        resp2 = await comm2.receive_json_from()
        assert resp1["data"]["ping"] is True
        assert resp2["data"]["ping"] is True

        await comm1.disconnect()
        await comm2.disconnect()
