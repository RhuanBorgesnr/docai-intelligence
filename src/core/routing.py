"""WebSocket URL routing for Django Channels."""
from django.urls import re_path

from orchestrator.consumers import (
    DashboardConsumer,
    EventsConsumer,
    AgentStatusConsumer,
    NotificationsConsumer,
)

websocket_urlpatterns = [
    # Real-time operational dashboard updates
    re_path(r"ws/dashboard/$", DashboardConsumer.as_asgi()),
    # Live event stream (case events, agent actions)
    re_path(r"ws/events/$", EventsConsumer.as_asgi()),
    # Agent status updates (heartbeat, task progress)
    re_path(r"ws/agents/$", AgentStatusConsumer.as_asgi()),
    # User-specific notifications
    re_path(r"ws/notifications/$", NotificationsConsumer.as_asgi()),
]
