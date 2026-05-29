"""
Sprint 2 Integration - Coordena todos os serviços de Sprint 2.

Este arquivo demonstra e coordena:
- Agent Runner (execução de agentes)
- Approval Gateway (aprovações)
- DocAI Adapter (integração com Document Intelligence)
- Notification Service (notificações)
- Inter-Agent Bus (comunicação entre agentes)
- Observabilidade (tracing + métricas)
"""

import asyncio
import logging
from typing import Any, Dict, Optional
import uuid

# Imports de Sprint 2
from agent_runtime.runner import AgentRunner, AgentExecutionStatus, AgentType
from agent_runtime.prompt_registry import PromptRegistry
from agent_runtime.inter_agent_bus import InterAgentBus, CommandPriority
from approvals.gateway import ApprovalGateway, ApprovalDecision, ApprovalPriority, ApprovalPolicy
from notifications.service import NotificationService, NotificationChannel
from orchestrator.docai_adapter import DocAIAdapter, DocumentType, AnalysisStatus
from orchestrator.observability import (
    Tracer, MetricsCollector, ObservabilityContext,
    log_structured
)

logger = logging.getLogger(__name__)


class Sprint2Orchestrator:
    """Coordenador de Sprint 2 - integra todos os componentes."""
    
    def __init__(self, llm_provider: str = "openai"):
        self.agent_runner = AgentRunner(llm_provider=llm_provider)
        self.docai_adapter = DocAIAdapter()
        self.approval_gateway = ApprovalGateway()
        self.notification_service = NotificationService()
        self.inter_agent_bus = InterAgentBus()
    
    async def process_lead_end_to_end(
        self,
        lead_id: str,
        lead_data: Dict[str, Any],
        correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fluxo completo de um lead: intake -> SDR -> Sales -> Approval.
        
        Args:
            lead_id: ID do lead
            lead_data: Dados do lead
            correlation_id: ID para rastreamento distribuído
        
        Returns:
            Resultado final do fluxo
        """
        
        correlation_id = correlation_id or str(uuid.uuid4())[:16]
        trace_id = Tracer.start_trace(correlation_id)
        
        logger.info(
            f"Iniciando fluxo de lead: {lead_id} "
            f"(correlation_id={correlation_id})"
        )
        
        # =================================================================
        # STEP 1: Intake Agent - Processa lead inicial
        # =================================================================
        with ObservabilityContext(
            operation_name="intake_processing",
            component="intake_agent",
            trace_id=trace_id
        ) as span:
            
            span.add_tag("lead_id", lead_id)
            
            # Executa Intake Agent
            intake_result = await self.agent_runner.execute_agent_command(
                agent_type=AgentType.INTAKE,
                context={
                    "lead_data": lead_data,
                },
                correlation_id=correlation_id
            )
            
            if not intake_result.is_success():
                logger.error(f"Intake falhou: {intake_result.error}")
                span.add_log(f"Intake failed: {intake_result.error}", level="error")
                return {
                    "status": "failed",
                    "stage": "intake",
                    "error": intake_result.error
                }
            
            span.add_tag("lead_quality", intake_result.output.get("lead_quality", "unknown"))
            
            # Notifica resultado
            await NotificationService.send_notification(
                notification_id=str(uuid.uuid4())[:16],
                case_id=lead_id,
                channel=NotificationChannel.LOG,
                recipient="system",
                template_name="intake_completed",
                context={
                    "lead_id": lead_id,
                    "quality": intake_result.output.get("lead_quality", "unknown")
                }
            )
            
            MetricsCollector.increment_counter(
                "intake.processed",
                labels={"quality": intake_result.output.get("lead_quality", "unknown")}
            )
        
        # Se lead não foi qualificado, pare aqui
        if not intake_result.output.get("extracted_info"):
            logger.warning(f"Lead descartado: {lead_id}")
            return {
                "status": "discarded",
                "stage": "intake",
                "reason": "Informações insuficientes"
            }
        
        # =================================================================
        # STEP 2: SDR Agent - Qualifica e prepara para Closer
        # =================================================================
        with ObservabilityContext(
            operation_name="sdr_qualification",
            component="sdr_agent",
            trace_id=trace_id
        ) as span:
            
            # Usa Inter-Agent Bus para comunicação
            sdr_command = await self.inter_agent_bus.send_command(
                case_id=lead_id,
                correlation_id=correlation_id,
                source_agent="intake",
                target_agent="sdr",
                command_name="qualify_lead",
                payload={
                    "lead_id": lead_id,
                    "lead_data": lead_data,
                    "extracted_info": intake_result.output.get("extracted_info", {})
                },
                priority=CommandPriority.HIGH,
                wait_for_response=False  # Assincrônico
            )
            
            span.add_tag("sdr_command_id", sdr_command.command_id)
            
            logger.info(f"Comando SDR enviado: {sdr_command.command_id}")
            
            MetricsCollector.increment_counter(
                "sdr.command.sent",
                labels={"command": "qualify_lead"}
            )
        
        # =================================================================
        # STEP 3: DocAI Analysis (paralelo)
        # =================================================================
        if lead_data.get("documents"):
            with ObservabilityContext(
                operation_name="docai_analysis",
                component="docai_adapter",
                trace_id=trace_id
            ) as span:
                
                document_path = lead_data["documents"][0]
                analysis_id = str(uuid.uuid4())[:16]
                
                try:
                    docai_result = await self.docai_adapter.process_document_end_to_end(
                        analysis_id=analysis_id,
                        case_id=lead_id,
                        document_path=document_path,
                        document_type=DocumentType.BALANCE_SHEET,
                        correlation_id=correlation_id
                    )
                    
                    span.add_tag("analysis_id", analysis_id)
                    span.add_tag("confidence", docai_result.confidence)
                    
                    # Se confiança baixa, marca para review
                    if docai_result.needs_manual_review:
                        span.add_log("Manual review required", level="warning")
                    
                    # Notifica conclusão da análise
                    await NotificationService.send_notification(
                        notification_id=str(uuid.uuid4())[:16],
                        case_id=lead_id,
                        channel=NotificationChannel.LOG,
                        recipient="system",
                        template_name="analysis_completed",
                        context={
                            "document_type": DocumentType.BALANCE_SHEET.value,
                            "case_id": lead_id,
                            "confidence": f"{docai_result.confidence:.1%}",
                            "status": docai_result.status.value
                        }
                    )
                    
                    MetricsCollector.record_histogram(
                        "docai.analysis.confidence",
                        docai_result.confidence,
                        labels={"document_type": DocumentType.BALANCE_SHEET.value}
                    )
                
                except Exception as e:
                    logger.error(f"DocAI analysis falhou: {str(e)}")
                    span.add_log(f"DocAI analysis failed: {str(e)}", level="error")
        
        # =================================================================
        # STEP 4: Simula Sales Agent (para demo)
        # =================================================================
        with ObservabilityContext(
            operation_name="sales_proposal",
            component="sales_agent",
            trace_id=trace_id
        ) as span:
            
            # Executa Sales Agent
            sales_result = await self.agent_runner.execute_agent_command(
                agent_type=AgentType.SALES,
                context={
                    "opportunity": {
                        "lead_id": lead_id,
                        "lead_data": lead_data
                    },
                    "docai_analysis": intake_result.output.get("extracted_info", {}),
                    "negotiation_history": []
                },
                correlation_id=correlation_id
            )
            
            if not sales_result.is_success():
                logger.error(f"Sales proposal falhou: {sales_result.error}")
                span.add_log(f"Proposal generation failed", level="error")
            else:
                proposal_value = sales_result.output.get("proposal", {}).get("total_value", 0)
                span.add_tag("proposal_value", proposal_value)
                
                # =============================================================
                # STEP 5: Approval Gateway - Pede aprovação se > threshold
                # =============================================================
                if proposal_value > 10000:  # > 10k requer aprovação
                    with ObservabilityContext(
                        operation_name="approval_request",
                        component="approval_gateway",
                        trace_id=trace_id
                    ) as approval_span:
                        
                        approval_id = str(uuid.uuid4())[:16]
                        
                        policy = ApprovalPolicy(
                            requires_approval=True,
                            approval_fields=["total_value", "terms"],
                            approvers=["sales_manager@company.com"],
                            deadline_minutes=120,
                            escalation_deadline_minutes=60,
                            priority=ApprovalPriority.URGENT
                        )
                        
                        approval = await self.approval_gateway.request_approval(
                            approval_id=approval_id,
                            case_id=lead_id,
                            correlation_id=correlation_id,
                            agent_type="sales_agent",
                            action="send_proposal",
                            data_to_approve=sales_result.output,
                            affected_fields=["total_value", "discount", "terms"],
                            context={
                                "lead": lead_data,
                                "proposal": sales_result.output
                            },
                            policy=policy
                        )
                        
                        approval_span.add_tag("approval_id", approval_id)
                        approval_span.add_tag("deadline", approval.deadline_at.isoformat())
                        
                        # Envia notificação de aprovação pendente
                        await NotificationService.send_notification(
                            notification_id=str(uuid.uuid4())[:16],
                            case_id=lead_id,
                            channel=NotificationChannel.EMAIL,
                            recipient="sales_manager@company.com",
                            template_name="approval_requested",
                            context={
                                "case_id": lead_id,
                                "action": "send_proposal",
                                "agent_name": "Sales Agent",
                                "deadline": approval.deadline_at.isoformat(),
                                "fields": ", ".join(approval.affected_fields),
                                "approval_link": f"http://localhost:8000/approvals/{approval_id}/"
                            },
                            priority="high"
                        )
                        
                        MetricsCollector.increment_counter(
                            "approval.requested",
                            labels={"action": "send_proposal"}
                        )
                        
                        # Em produção, aqui faria polling ou webhook
                        # Para demo, simula aprovação automática após 2s
                        await asyncio.sleep(2)
                        
                        approval = await self.approval_gateway.decide_approval(
                            approval_id=approval_id,
                            decision=ApprovalDecision.APPROVED,
                            approved_by="sales_manager@company.com",
                            comment="Proposta dentro dos padrões"
                        )
                        
                        approval_span.add_tag("decision", approval.status)
                        
                        MetricsCollector.increment_counter(
                            "approval.completed",
                            labels={"action": "send_proposal", "decision": approval.status}
                        )
        
        # =================================================================
        # FINAL: Retorna resultado agregado
        # =================================================================
        final_result = {
            "status": "completed",
            "lead_id": lead_id,
            "correlation_id": correlation_id,
            "trace_id": trace_id,
            "stages": {
                "intake": {
                    "status": "success",
                    "quality": intake_result.output.get("lead_quality", "unknown"),
                    "latency_ms": intake_result.metrics.total_latency_ms if intake_result.metrics else 0
                },
                "sdr": {
                    "status": "sent",
                    "command_id": sdr_command.command_id
                },
                "sales": {
                    "status": sales_result.status.value,
                    "proposal_value": sales_result.output.get("proposal", {}).get("total_value", 0) if sales_result.is_success() else 0
                }
            }
        }
        
        logger.info(f"Lead processing completo: {lead_id}")
        
        # Log estruturado com trace
        log_structured(
            level="info",
            message="Lead processing completed",
            trace_id=trace_id,
            context={
                "lead_id": lead_id,
                "stages_completed": list(final_result["stages"].keys()),
                "correlation_id": correlation_id
            }
        )
        
        return final_result


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

async def example_sprint2_workflow():
    """Exemplo de uso do Sprint 2 completo."""
    
    orchestrator = Sprint2Orchestrator(llm_provider="openai")
    
    # Lead de exemplo
    lead_data = {
        "name": "Acme Corp",
        "email": "contact@acmecorp.com",
        "phone": "+55 11 98765-4321",
        "industry": "Technology",
        "documents": ["/documents/balance_sheet.pdf"]
    }
    
    # Processa lead
    result = await orchestrator.process_lead_end_to_end(
        lead_id="lead_001",
        lead_data=lead_data,
        correlation_id="corr_001"
    )
    
    print("\n" + "="*70)
    print("SPRINT 2 WORKFLOW RESULT")
    print("="*70)
    print(f"Lead ID: {result['lead_id']}")
    print(f"Status: {result['status']}")
    print(f"Trace ID: {result['trace_id']}")
    print(f"Stages: {list(result['stages'].keys())}")
    
    # Exibe métricas
    print("\n" + "="*70)
    print("METRICS SUMMARY")
    print("="*70)
    summary = MetricsCollector.get_metrics_summary()
    for metric_name, stats in summary.items():
        print(f"{metric_name}:")
        print(f"  Count: {stats['count']}")
        print(f"  Avg: {stats['avg']:.2f}")
        print(f"  Min: {stats['min']:.2f}")
        print(f"  Max: {stats['max']:.2f}")
    
    # Exibe trace
    print("\n" + "="*70)
    print("TRACE DETAILS")
    print("="*70)
    trace = Tracer.get_trace(result['trace_id'])
    print(f"Total Spans: {trace['span_count']}")
    print(f"Total Duration: {trace['total_duration_ms']:.2f}ms")
    for span in trace['spans']:
        print(f"  - {span['operation_name']} ({span['component']}): {span['duration_ms']:.2f}ms")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_sprint2_workflow())
