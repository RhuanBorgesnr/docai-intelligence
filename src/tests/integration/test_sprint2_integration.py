"""
Sprint 2 Integration Tests - Testa todos os componentes novos.

Testes incluem:
- Agent Runner (execução e retries)
- Approval Gateway (aprovação e deadline)
- DocAI Adapter (async polling)
- Notification Service (multi-channel)
- Inter-Agent Communication (command bus)
- Observabilidade (tracing)
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

# Imports
from agent_runtime.runner import (
    AgentRunner, AgentType, AgentExecutionStatus, LLMExecutor
)
from agent_runtime.prompt_registry import PromptRegistry, OutputSchema, PromptPolicy
from agent_runtime.inter_agent_bus import (
    InterAgentBus, CommandStatus, CommandContract, CommandPriority
)
from approvals.gateway import (
    ApprovalGateway, ApprovalDecision, ApprovalPriority, ApprovalPolicy
)
from notifications.service import (
    NotificationService, NotificationChannel, NotificationStatus
)
from orchestrator.docai_adapter import (
    DocAIAdapter, DocumentType, AnalysisStatus
)
from orchestrator.observability import Tracer, MetricsCollector


pytestmark = pytest.mark.django_db(transaction=True)


# =============================================================================
# TEST: AGENT RUNNER
# =============================================================================

@pytest.mark.asyncio
async def test_agent_runner_successful_execution():
    """Testa execução bem-sucedida de um agente."""
    
    runner = AgentRunner(llm_provider="openai")
    
    result = await runner.execute_agent_command(
        agent_type=AgentType.INTAKE,
        context={
            "lead_data": {"name": "Test Co", "email": "test@company.com"}
        },
        correlation_id="test_001"
    )
    
    assert result.status in [AgentExecutionStatus.SUCCESS, AgentExecutionStatus.TIMEOUT]
    assert result.execution_id is not None
    assert result.metrics is not None


@pytest.mark.asyncio
async def test_agent_runner_caching():
    """Testa que cache de execução funciona."""
    
    runner = AgentRunner(llm_provider="openai")
    
    context = {"test": "data"}
    
    # Primeira execução
    result1 = await runner.execute_agent_command(
        agent_type=AgentType.INTAKE,
        context=context,
        correlation_id="test_cache_1",
        use_cache=True
    )
    
    # Segunda execução - deveria usar cache
    result2 = await runner.execute_agent_command(
        agent_type=AgentType.INTAKE,
        context=context,
        correlation_id="test_cache_2",
        use_cache=True
    )
    
    assert result1.execution_id == result2.execution_id  # Mesmo ID = cache hit
    assert result2.cache_hit == True


def test_agent_runner_schema_validation():
    """Testa validação de schema."""
    
    schema = OutputSchema(
        properties={
            "name": {"type": "string"},
            "age": {"type": "number"}
        },
        required=["name", "age"]
    )
    
    # Válido
    valid_output = {"name": "John", "age": 30}
    is_valid, error = schema.validate(valid_output)
    assert is_valid is True
    assert error is None
    
    # Inválido - campo obrigatório faltando
    invalid_output = {"name": "John"}
    is_valid, error = schema.validate(invalid_output)
    assert is_valid is False
    assert "age" in error


@pytest.mark.asyncio
async def test_agent_runner_retry_on_failure():
    """Testa retry automático em falhas."""
    
    runner = AgentRunner(llm_provider="openai")
    
    # Simula falha
    with patch.object(runner.llm_executor, 'execute_prompt', return_value=(None, {"error": "timeout"})):
        result = await runner.execute_agent_command(
            agent_type=AgentType.INTAKE,
            context={"data": "test"},
            correlation_id="test_retry",
            retry_on_failure=True
        )
    
    # Deveria ter tentado multiple vezes
    assert result.metrics.retry_count > 0


# =============================================================================
# TEST: APPROVAL GATEWAY
# =============================================================================

@pytest.mark.asyncio
async def test_approval_gateway_request():
    """Testa criação de request de aprovação."""
    
    approval = await ApprovalGateway.request_approval(
        approval_id="appr_001",
        case_id="case_001",
        correlation_id="corr_001",
        agent_type="sales_agent",
        action="send_proposal",
        data_to_approve={"amount": 50000},
        affected_fields=["amount"],
        context={"proposal": "data"}
    )
    
    assert approval.approval_id == "appr_001"
    assert approval.status == "pending"
    assert approval.case_id == "case_001"


@pytest.mark.asyncio
async def test_approval_gateway_decision():
    """Testa decisão de aprovação."""
    
    # Request
    approval = await ApprovalGateway.request_approval(
        approval_id="appr_002",
        case_id="case_002",
        correlation_id="corr_002",
        agent_type="sales_agent",
        action="send_proposal",
        data_to_approve={"amount": 50000},
        affected_fields=["amount"],
        context={},
        policy=ApprovalPolicy(
            requires_approval=True,
            approval_fields=["amount"],
            approvers=["manager@company.com"],
            deadline_minutes=60,
            escalation_deadline_minutes=30,
            priority=ApprovalPriority.ROUTINE,
        ),
    )
    
    assert approval.status == "pending"
    
    # Decide
    approval = await ApprovalGateway.decide_approval(
        approval_id="appr_002",
        decision=ApprovalDecision.APPROVED,
        approved_by="manager@company.com",
        comment="Good to go"
    )
    
    assert approval.status == "approved"
    assert approval.approved_by == "manager@company.com"


@pytest.mark.asyncio
async def test_approval_gateway_expiration():
    """Testa expiração de aprovação."""
    
    # Request com deadline muito curto
    approval = await ApprovalGateway.request_approval(
        approval_id="appr_003",
        case_id="case_003",
        correlation_id="corr_003",
        agent_type="sales_agent",
        action="send_proposal",
        data_to_approve={"amount": 50000},
        affected_fields=["amount"],
        context={},
        policy=ApprovalPolicy(
            requires_approval=True,
            approval_fields=["amount"],
            approvers=["manager@company.com"],
            deadline_minutes=0,  # Já expirou!
            escalation_deadline_minutes=0,
            priority=ApprovalPriority.CRITICAL
        )
    )
    
    assert approval.is_expired is True


@pytest.mark.asyncio
async def test_approval_list_pending():
    """Testa listagem de aprovações pendentes."""
    from asgiref.sync import sync_to_async
    
    # Cria 2 requests
    await ApprovalGateway.request_approval(
        approval_id="appr_004",
        case_id="case_004",
        correlation_id="corr_004",
        agent_type="sales",
        action="test",
        data_to_approve={},
        affected_fields=[],
        context={}
    )
    
    await ApprovalGateway.request_approval(
        approval_id="appr_005",
        case_id="case_005",
        correlation_id="corr_005",
        agent_type="sales",
        action="test",
        data_to_approve={},
        affected_fields=[],
        context={}
    )
    
    pending = await sync_to_async(ApprovalGateway.list_pending_approvals, thread_sensitive=True)()
    
    assert len(pending) >= 2
    assert all(a.status == "pending" for a in pending)


# =============================================================================
# TEST: DOCAI ADAPTER
# =============================================================================

@pytest.mark.asyncio
async def test_docai_adapter_submit():
    """Testa submissão de documento."""
    
    result = await DocAIAdapter.submit_document(
        analysis_id="ana_001",
        case_id="case_001",
        document_path="/documents/test.pdf",
        document_type=DocumentType.BALANCE_SHEET,
        correlation_id="corr_001"
    )
    
    assert result.analysis_id == "ana_001"
    assert result.status in [AnalysisStatus.PENDING, AnalysisStatus.PROCESSING]


@pytest.mark.asyncio
async def test_docai_adapter_normalize():
    """Testa normalização de output."""
    
    from orchestrator.docai_adapter import DocumentAnalysisResult
    
    raw_result = DocumentAnalysisResult(
        analysis_id="ana_002",
        case_id="case_002",
        document_type=DocumentType.INVOICE,
        status=AnalysisStatus.COMPLETED,
        extracted_data={"total": 1000},
        entities={"issuer": "Company A"},
        relationships={},
        confidence=0.92,
        field_confidences={"total": 0.95, "issuer": 0.90},
        warnings=[]
    )
    
    normalized = DocAIAdapter.normalize_output(raw_result)
    
    assert normalized.confidence >= 0.85
    assert normalized.is_confident == True


# =============================================================================
# TEST: NOTIFICATION SERVICE
# =============================================================================

@pytest.mark.asyncio
async def test_notification_email_send():
    """Testa envio de email."""
    
    notification = await NotificationService.send_notification(
        notification_id="notif_001",
        case_id="case_001",
        channel=NotificationChannel.EMAIL,
        recipient="test@company.com",
        subject="Test Subject",
        message="Test message",
        priority="high"
    )
    
    assert notification.notification_id == "notif_001"
    assert notification.status in [NotificationStatus.SENT, NotificationStatus.FAILED]


@pytest.mark.asyncio
async def test_notification_log_send():
    """Testa envio como log estruturado."""
    
    notification = await NotificationService.send_notification(
        notification_id="notif_002",
        case_id="case_002",
        channel=NotificationChannel.LOG,
        recipient="system",
        subject="Log Entry",
        message="This is a log"
    )
    
    assert notification.status == NotificationStatus.SENT


@pytest.mark.asyncio
async def test_notification_template():
    """Testa template de notificação."""
    
    notification = await NotificationService.send_notification(
        notification_id="notif_003",
        case_id="case_003",
        channel=NotificationChannel.LOG,
        recipient="system",
        template_name="approval_requested",
        context={
            "case_id": "case_003",
            "action": "test_action",
            "agent_name": "Test Agent",
            "deadline": "2025-01-01T12:00:00Z",
            "fields": "field1, field2",
            "approval_link": "http://example.com"
        }
    )
    
    assert notification.status == NotificationStatus.SENT


# =============================================================================
# TEST: INTER-AGENT BUS
# =============================================================================

@pytest.mark.asyncio
async def test_inter_agent_bus_send_command():
    """Testa envio de comando entre agentes."""
    
    command = await InterAgentBus.send_command(
        case_id="case_001",
        correlation_id="corr_001",
        source_agent="intake",
        target_agent="sdr",
        command_name="qualify_lead",
        payload={"lead_id": "lead_001"},
        wait_for_response=False
    )
    
    assert command.source_agent == "intake"
    assert command.target_agent == "sdr"
    assert command.status == CommandStatus.SENT or command.status == CommandStatus.PENDING


@pytest.mark.asyncio
async def test_inter_agent_bus_list_commands():
    """Testa listagem de comandos."""
    from asgiref.sync import sync_to_async
    
    # Envia comando
    await InterAgentBus.send_command(
        case_id="case_test",
        correlation_id="corr_test",
        source_agent="intake",
        target_agent="sdr",
        command_name="qualify_lead",
        payload={"test": "data"},
        wait_for_response=False
    )
    
    # Lista
    commands = await sync_to_async(InterAgentBus.list_commands, thread_sensitive=True)(case_id="case_test")
    
    assert len(commands) > 0
    assert all(c.case_id == "case_test" for c in commands)


# =============================================================================
# TEST: OBSERVABILITY
# =============================================================================

def test_observability_tracing():
    """Testa sistema de tracing."""
    
    trace_id = Tracer.start_trace("test_trace_001")
    
    span = Tracer.start_span(
        operation_name="test_op",
        component="test_component",
        trace_id=trace_id,
        tags={"key": "value"}
    )
    
    span.add_log("Test log message")
    Tracer.end_span(span.span_id, status="completed")
    
    retrieved_span = Tracer.get_span(span.span_id)
    
    assert retrieved_span is not None
    assert retrieved_span.status == "completed"
    assert len(retrieved_span.logs) > 0


def test_observability_metrics():
    """Testa coleta de métricas."""
    
    MetricsCollector.increment_counter("test.counter", amount=5)
    MetricsCollector.record_gauge("test.gauge", value=100)
    MetricsCollector.record_histogram("test.latency", value=250)
    
    summary = MetricsCollector.get_metrics_summary()
    
    assert "test.counter" in summary
    assert summary["test.counter"]["sum"] >= 5


def test_observability_context_manager():
    """Testa context manager de observabilidade."""
    
    from orchestrator.observability import ObservabilityContext
    
    trace_id = Tracer.start_trace("test_trace_002")
    
    with ObservabilityContext(
        operation_name="test_operation",
        component="test_component",
        trace_id=trace_id
    ) as span:
        assert span is not None
        assert span.trace_id == trace_id
    
    # Span deve estar completo
    assert span.status == "completed"


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
