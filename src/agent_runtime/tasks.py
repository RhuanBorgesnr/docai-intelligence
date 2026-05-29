"""Celery tasks for durable inter-agent command processing."""
from __future__ import annotations

from asgiref.sync import async_to_sync
from celery import shared_task

from agent_runtime.inter_agent_bus import InterAgentBus


@shared_task
def process_agent_command_batch(agent_name: str, max_concurrent: int = 5) -> int:
    """Process one durable command batch for a target agent."""
    return async_to_sync(InterAgentBus.process_pending_batch)(
        agent_name=agent_name,
        max_concurrent=max_concurrent,
    )
