"""Agent runtime models."""
from django.db import models

from orchestrator.enums import AgentCommandStatus, Priority, PromptLifecycleStatus


class AgentCommand(models.Model):
    """Command sent to an agent."""

    command_id = models.CharField(max_length=128, unique=True)
    case = models.ForeignKey("orchestrator.Case", on_delete=models.CASCADE, related_name="agent_commands")
    source_agent = models.CharField(max_length=100, blank=True)
    command_type = models.CharField(max_length=100)
    target_agent = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=AgentCommandStatus.choices,
        default=AgentCommandStatus.PENDING,
    )
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    correlation_id = models.CharField(max_length=100, db_index=True)
    trace_id = models.CharField(max_length=100, blank=True)
    causation_id = models.CharField(max_length=128, blank=True)
    idempotency_key = models.CharField(max_length=128, blank=True, db_index=True)
    loop_signature = models.CharField(max_length=128, blank=True, db_index=True)
    hop_count = models.PositiveIntegerField(default=0)
    input_payload = models.JSONField(default=dict)
    expected_output_schema = models.CharField(max_length=100, blank=True)
    contract_version = models.CharField(max_length=20, default="1.0")
    timeout_seconds = models.PositiveIntegerField(default=30)
    max_retries = models.PositiveIntegerField(default=3)
    retry_count = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(auto_now_add=True)
    leased_until = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "available_at"]),
            models.Index(fields=["target_agent", "status"]),
            models.Index(fields=["case", "status"]),
            models.Index(fields=["loop_signature"]),
        ]


class AgentResponse(models.Model):
    """Response returned by an agent for a command."""

    response_id = models.CharField(max_length=128, unique=True)
    command = models.ForeignKey(AgentCommand, on_delete=models.CASCADE, related_name="responses")
    agent_id = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=AgentCommandStatus.choices)
    output_payload = models.JSONField(default=dict)
    quality = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    prompt_version = models.CharField(max_length=20, blank=True)
    policy_version = models.CharField(max_length=20, blank=True)
    schema_version = models.CharField(max_length=20, blank=True)
    model_name = models.CharField(max_length=120, blank=True)
    provider = models.CharField(max_length=50, blank=True)
    trace_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PromptDefinition(models.Model):
    """Durable prompt registry with tenant isolation and rollout control."""

    agent_type = models.CharField(max_length=100)
    tenant_id = models.CharField(max_length=100, default="default")
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=PromptLifecycleStatus.choices, default=PromptLifecycleStatus.DRAFT)
    description = models.TextField(blank=True)
    content = models.TextField()
    variables = models.JSONField(default=dict, blank=True)
    output_schema = models.JSONField(default=dict, blank=True)
    policy = models.JSONField(default=dict, blank=True)
    content_hash = models.CharField(max_length=64, db_index=True)
    created_by = models.CharField(max_length=120, blank=True)
    rollback_from_version = models.PositiveIntegerField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["agent_type", "tenant_id", "version"], name="uniq_prompt_definition_version"),
        ]
        indexes = [
            models.Index(fields=["agent_type", "tenant_id", "status"]),
            models.Index(fields=["content_hash"]),
        ]

# Import cost tracker model so Django discovers it
from agent_runtime.cost_tracker import AgentExecution  # noqa: E402, F401
