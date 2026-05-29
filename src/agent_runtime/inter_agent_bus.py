"""
Inter-Agent Communication - Bus de comunicação entre agentes.

Responsabilidades:
- Registro de contratos entre agentes
- Execução de comandos assíncronos
- Rastreamento de respostas
- Timeout handling
- Retry logic
- Context propagation
- Failure escalation
"""

import logging
import asyncio
from typing import Any, Dict, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import hashlib
import json
import uuid

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from agent_runtime.models import AgentCommand as AgentCommandRecord, AgentResponse
from orchestrator.enums import AgentCommandStatus, Priority
from orchestrator.models import Case

logger = logging.getLogger(__name__)


class CommandStatus(str, Enum):
    """Status de um comando entre agentes."""
    PENDING = "pending"
    SENT = "sent"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class CommandPriority(str, Enum):
    """Prioridade de execução de um comando."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CommandContract:
    """Define o contrato de um comando entre agentes."""
    
    command_name: str
    source_agent: str  # Qual agente emite?
    target_agent: str  # Qual agente recebe?
    
    # Schema
    input_schema: Dict[str, Any]  # JSON schema esperado
    output_schema: Dict[str, Any]  # JSON schema que será retornado
    
    # Configuração
    timeout_seconds: int = 30
    max_retries: int = 3
    requires_approval: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "command_name": self.command_name,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "requires_approval": self.requires_approval
        }


@dataclass
class AgentCommand:
    """Um comando enviado de um agente para outro."""
    
    command_id: str
    case_id: str
    correlation_id: str
    
    source_agent: str
    target_agent: str
    command_name: str
    
    payload: Dict[str, Any]
    priority: CommandPriority = CommandPriority.NORMAL
    
    # Timing
    created_at: datetime = None
    sent_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Status
    status: CommandStatus = CommandStatus.PENDING
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    @property
    def elapsed_ms(self) -> float:
        """Tempo decorrido até agora."""
        end_time = self.completed_at or datetime.utcnow()
        return (end_time - self.created_at).total_seconds() * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "command_id": self.command_id,
            "case_id": self.case_id,
            "correlation_id": self.correlation_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "command_name": self.command_name,
            "payload": self.payload,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status.value,
            "response": self.response,
            "error": self.error,
            "retry_count": self.retry_count,
            "elapsed_ms": self.elapsed_ms
        }


class InterAgentBus:
    """Bus central de comunicação entre agentes."""
    
    # Registro de contratos
    _contracts: Dict[str, CommandContract] = {}
    
    # Handlers registrados
    _handlers: Dict[str, Callable] = {}
    
    @classmethod
    def register_contract(cls, contract: CommandContract):
        """Registra um novo contrato entre agentes."""
        contract_key = f"{contract.source_agent}:{contract.command_name}"
        cls._contracts[contract_key] = contract
        
        logger.info(
            f"Contrato registrado: {contract.source_agent} -> "
            f"{contract.target_agent} ({contract.command_name})"
        )
    
    @classmethod
    def register_handler(
        cls,
        agent_name: str,
        command_name: str,
        handler: Callable
    ):
        """Registra um handler para um comando."""
        handler_key = f"{agent_name}:{command_name}"
        cls._handlers[handler_key] = handler
        
        logger.info(f"Handler registrado: {handler_key}")
    
    @classmethod
    def get_contract(
        cls,
        source_agent: str,
        command_name: str
    ) -> Optional[CommandContract]:
        """Recupera contrato."""
        contract_key = f"{source_agent}:{command_name}"
        return cls._contracts.get(contract_key) or cls._contracts.get(f"*:{command_name}")
    
    @classmethod
    async def send_command(
        cls,
        case_id: str,
        correlation_id: str,
        source_agent: str,
        target_agent: str,
        command_name: str,
        payload: Dict[str, Any],
        priority: CommandPriority = CommandPriority.NORMAL,
        wait_for_response: bool = True,
        timeout_override: Optional[int] = None
    ) -> AgentCommand:
        """
        Envia um comando de um agente para outro.
        
        Args:
            case_id: Case relacionado
            correlation_id: Para rastreamento distribuído
            source_agent: Agente que envia
            target_agent: Agente que recebe
            command_name: Nome do comando
            payload: Dados do comando
            priority: Prioridade
            wait_for_response: Esperar resposta?
            timeout_override: Timeout customizado (segundos)
        
        Returns:
            AgentCommand com status atualizado
        """
        
        # Valida contrato
        contract = cls.get_contract(source_agent, command_name)
        if not contract:
            raise ValueError(
                f"Contrato não encontrado: "
                f"{source_agent} -> {target_agent} ({command_name})"
            )
        
        if contract.target_agent != target_agent:
            raise ValueError(
                f"Target agent incorreto: esperado "
                f"{contract.target_agent}, recebido {target_agent}"
            )
        
        # Cria comando
        command_id = str(uuid.uuid4())[:16]
        command = await cls._create_command(
            command_id=command_id,
            case_id=case_id,
            correlation_id=correlation_id,
            source_agent=source_agent,
            target_agent=target_agent,
            command_name=command_name,
            payload=payload,
            priority=priority,
            contract=contract,
        )
        
        logger.info(
            f"Comando enviado: {command_id} "
            f"({source_agent} -> {target_agent}, {command_name})"
        )
        
        # Se esperar resposta, aguarda
        if wait_for_response:
            timeout = timeout_override or contract.timeout_seconds
            
            try:
                command = await cls._wait_for_response(
                    command_id=command_id,
                    timeout_seconds=timeout,
                    max_retries=contract.max_retries
                )
            except asyncio.TimeoutError:
                command.status = CommandStatus.TIMEOUT
                command.error = f"Timeout após {timeout} segundos"
                logger.error(f"Comando expirou: {command_id}")
        
        return command
    
    @classmethod
    async def _wait_for_response(
        cls,
        command_id: str,
        timeout_seconds: int = 30,
        max_retries: int = 3
    ) -> AgentCommand:
        """Aguarda resposta de um comando."""
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            command = await cls.get_command(command_id)
            
            if not command:
                raise ValueError(f"Comando não encontrado: {command_id}")
            
            # Verifica se completou
            if command.status in [
                CommandStatus.COMPLETED,
                CommandStatus.FAILED,
                CommandStatus.TIMEOUT
            ]:
                return command
            
            # Verifica timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_seconds:
                raise asyncio.TimeoutError(
                    f"Timeout aguardando resposta: {command_id}"
                )
            
            # Poll a cada 100ms
            await asyncio.sleep(0.1)
    
    @classmethod
    async def process_command_queue(
        cls,
        agent_name: str,
        max_concurrent: int = 5
    ):
        """Loop contínuo de processamento para ambientes locais ou workers dedicados."""
        logger.info(f"Iniciando processamento da fila para {agent_name}")

        while True:
            try:
                processed = await cls.process_pending_batch(
                    agent_name=agent_name,
                    max_concurrent=max_concurrent,
                )
                if processed == 0:
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(
                    f"Erro ao processar comando para {agent_name}: {str(e)}",
                    exc_info=True
                )
                await asyncio.sleep(1.0)

    @classmethod
    async def process_pending_batch(
        cls,
        agent_name: str,
        max_concurrent: int = 5,
    ) -> int:
        """Processa um batch de comandos persistidos para uso por workers Celery."""
        semaphore = asyncio.Semaphore(max_concurrent)
        commands = await cls._claim_pending_commands(
            agent_name=agent_name,
            limit=max_concurrent,
        )
        if not commands:
            return 0

        async def run_one(command: AgentCommand):
            async with semaphore:
                await cls._process_command(agent_name, command)

        await asyncio.gather(*(run_one(command) for command in commands))
        return len(commands)

    @classmethod
    async def _create_command(
        cls,
        command_id: str,
        case_id: str,
        correlation_id: str,
        source_agent: str,
        target_agent: str,
        command_name: str,
        payload: Dict[str, Any],
        priority: CommandPriority,
        contract: CommandContract,
    ) -> AgentCommand:
        return await sync_to_async(
            cls._create_command_sync,
            thread_sensitive=True,
        )(
            command_id,
            case_id,
            correlation_id,
            source_agent,
            target_agent,
            command_name,
            payload,
            priority,
            contract,
        )

    @classmethod
    def _create_command_sync(
        cls,
        command_id: str,
        case_id: str,
        correlation_id: str,
        source_agent: str,
        target_agent: str,
        command_name: str,
        payload: Dict[str, Any],
        priority: CommandPriority,
        contract: CommandContract,
    ) -> AgentCommand:
        case = cls._resolve_case(case_id=case_id, correlation_id=correlation_id)
        hop_count = int(payload.get("hop_count", 0))
        if hop_count >= 8:
            raise ValueError(f"Hop count excedido para comando {command_name}")

        idempotency_key = payload.get("idempotency_key") or cls._build_idempotency_key(
            case_id=case_id,
            source_agent=source_agent,
            target_agent=target_agent,
            command_name=command_name,
            payload=payload,
        )
        loop_signature = cls._build_loop_signature(case.tenant_id, case_id, source_agent, target_agent, command_name, payload)

        with transaction.atomic():
            existing = AgentCommandRecord.objects.filter(idempotency_key=idempotency_key).order_by("-created_at").first()
            if existing and existing.status not in [AgentCommandStatus.CANCELLED, AgentCommandStatus.FAILED, AgentCommandStatus.TIMED_OUT]:
                return cls._to_domain_command(existing)

            inflight_same_signature = AgentCommandRecord.objects.filter(
                loop_signature=loop_signature,
                status__in=[AgentCommandStatus.PENDING, AgentCommandStatus.DISPATCHED, AgentCommandStatus.RUNNING],
            ).count()
            if inflight_same_signature >= 3:
                raise ValueError(f"Possível loop detectado para assinatura {loop_signature}")

            record = AgentCommandRecord.objects.create(
                command_id=command_id,
                case=case,
                source_agent=source_agent,
                command_type=command_name,
                target_agent=target_agent,
                status=AgentCommandStatus.DISPATCHED,
                priority=cls._map_priority(priority),
                correlation_id=correlation_id,
                trace_id=correlation_id,
                idempotency_key=idempotency_key,
                loop_signature=loop_signature,
                hop_count=hop_count,
                input_payload={**payload, "hop_count": hop_count + 1},
                expected_output_schema=json.dumps(contract.output_schema, sort_keys=True)[:100],
                contract_version="1.0",
                timeout_seconds=contract.timeout_seconds,
                max_retries=contract.max_retries,
            )

        return cls._to_domain_command(record)

    @classmethod
    async def _claim_pending_commands(
        cls,
        agent_name: str,
        limit: int,
        lease_seconds: int = 60,
    ) -> List[AgentCommand]:
        return await sync_to_async(
            cls._claim_pending_commands_sync,
            thread_sensitive=True,
        )(agent_name, limit, lease_seconds)

    @classmethod
    def _claim_pending_commands_sync(
        cls,
        agent_name: str,
        limit: int,
        lease_seconds: int,
    ) -> List[AgentCommand]:
        now = timezone.now()
        lease_until = now + timezone.timedelta(seconds=lease_seconds)
        claimed: List[AgentCommand] = []

        with transaction.atomic():
            records = list(
                AgentCommandRecord.objects.select_for_update(skip_locked=True)
                .filter(
                    target_agent=agent_name,
                    status__in=[AgentCommandStatus.PENDING, AgentCommandStatus.DISPATCHED],
                    available_at__lte=now,
                )
                .order_by("created_at")[:limit]
            )

            for record in records:
                record.status = AgentCommandStatus.RUNNING
                record.started_at = now
                record.leased_until = lease_until
                record.save(update_fields=["status", "started_at", "leased_until", "updated_at"])
                claimed.append(cls._to_domain_command(record))

        return claimed

    @classmethod
    async def _process_command(
        cls,
        agent_name: str,
        command: AgentCommand
    ):
        """Processa um comando específico."""
        
        try:
            # Recupera handler
            handler_key = f"{agent_name}:{command.command_name}"
            handler = cls._handlers.get(handler_key)
            
            if not handler:
                raise ValueError(f"Handler não encontrado: {handler_key}")
            
            # Executa handler
            logger.info(f"Executando comando: {command.command_id}")
            
            response = await cls._call_handler(
                handler=handler,
                command=command,
                timeout_seconds=await cls._get_command_timeout(command.command_id)
            )

            command.response = response
            command.status = CommandStatus.COMPLETED
            command.completed_at = datetime.utcnow()
            await cls._mark_command_completed(command, response)
            
            logger.info(
                f"Comando completado: {command.command_id} "
                f"(elapsed={command.elapsed_ms:.0f}ms)"
            )
            
            await cls._emit_command_completed_event(command)
        
        except Exception as e:
            command.status = CommandStatus.FAILED
            command.error = str(e)
            command.completed_at = datetime.utcnow()
            await cls._mark_command_failed(command, str(e))
            
            logger.error(
                f"Falha ao processar comando: {command.command_id} ({str(e)})",
                exc_info=True
            )
            
            await cls._emit_command_failed_event(command)
    
    @classmethod
    async def _call_handler(
        cls,
        handler: Callable,
        command: AgentCommand,
        timeout_seconds: int
    ) -> Dict[str, Any]:
        """Chama handler com timeout."""
        
        try:
            # Se handler é async
            if asyncio.iscoroutinefunction(handler):
                response = await asyncio.wait_for(
                    handler(command),
                    timeout=timeout_seconds
                )
            else:
                # Se é sync, executa em executor
                loop = asyncio.get_event_loop()
                response = await asyncio.wait_for(
                    loop.run_in_executor(None, handler, command),
                    timeout=timeout_seconds
                )
            
            return response or {}
        
        except asyncio.TimeoutError:
            raise TimeoutError(f"Handler timeout após {timeout_seconds}s")
    
    @classmethod
    async def get_command(cls, command_id: str) -> Optional[AgentCommand]:
        """Recupera comando por ID."""
        return await sync_to_async(cls._get_command_sync, thread_sensitive=True)(command_id)
    
    @classmethod
    def list_commands(
        cls,
        case_id: Optional[str] = None,
        source_agent: Optional[str] = None,
        target_agent: Optional[str] = None,
        status: Optional[CommandStatus] = None
    ) -> List[AgentCommand]:
        """Lista comandos com filtros."""
        return cls._list_commands_sync(
            case_id=case_id,
            source_agent=source_agent,
            target_agent=target_agent,
            status=status,
        )

    @classmethod
    def _get_command_sync(cls, command_id: str) -> Optional[AgentCommand]:
        record = AgentCommandRecord.objects.filter(command_id=command_id).select_related("case").first()
        if not record:
            return None
        return cls._to_domain_command(record)

    @classmethod
    def _list_commands_sync(
        cls,
        case_id: Optional[str] = None,
        source_agent: Optional[str] = None,
        target_agent: Optional[str] = None,
        status: Optional[CommandStatus] = None,
    ) -> List[AgentCommand]:
        queryset = AgentCommandRecord.objects.select_related("case").all()

        if case_id:
            queryset = queryset.filter(case__external_ref=case_id)

        if source_agent:
            queryset = queryset.filter(source_agent=source_agent)

        if target_agent:
            queryset = queryset.filter(target_agent=target_agent)

        if status:
            queryset = queryset.filter(status=cls._map_status_to_record(status))

        return [cls._to_domain_command(record) for record in queryset.order_by("-created_at")]

    @classmethod
    async def _get_command_timeout(cls, command_id: str) -> int:
        return await sync_to_async(cls._get_command_timeout_sync, thread_sensitive=True)(command_id)

    @classmethod
    def _get_command_timeout_sync(cls, command_id: str) -> int:
        return AgentCommandRecord.objects.only("timeout_seconds").get(command_id=command_id).timeout_seconds

    @classmethod
    async def _mark_command_completed(cls, command: AgentCommand, response: Dict[str, Any]) -> None:
        await sync_to_async(cls._mark_command_completed_sync, thread_sensitive=True)(command, response)

    @classmethod
    def _mark_command_completed_sync(cls, command: AgentCommand, response: Dict[str, Any]) -> None:
        with transaction.atomic():
            record = AgentCommandRecord.objects.select_for_update().get(command_id=command.command_id)
            record.status = AgentCommandStatus.SUCCEEDED
            record.completed_at = timezone.now()
            record.leased_until = None
            record.last_error = ""
            record.save(update_fields=["status", "completed_at", "leased_until", "last_error", "updated_at"])
            AgentResponse.objects.create(
                response_id=str(uuid.uuid4())[:16],
                command=record,
                agent_id=record.target_agent,
                status=AgentCommandStatus.SUCCEEDED,
                output_payload=response,
                trace_id=record.trace_id,
            )

    @classmethod
    async def _mark_command_failed(cls, command: AgentCommand, error_message: str) -> None:
        await sync_to_async(cls._mark_command_failed_sync, thread_sensitive=True)(command, error_message)

    @classmethod
    def _mark_command_failed_sync(cls, command: AgentCommand, error_message: str) -> None:
        with transaction.atomic():
            record = AgentCommandRecord.objects.select_for_update().get(command_id=command.command_id)
            record.retry_count += 1
            record.last_error = error_message
            record.leased_until = None
            if record.retry_count < record.max_retries:
                record.status = AgentCommandStatus.DISPATCHED
                record.available_at = timezone.now() + timezone.timedelta(seconds=min(60, (2 ** record.retry_count) + cls._compute_jitter(record.command_id)))
            else:
                record.status = AgentCommandStatus.FAILED
                record.completed_at = timezone.now()
            record.save(update_fields=["retry_count", "last_error", "leased_until", "status", "available_at", "completed_at", "updated_at"])

    @classmethod
    def _resolve_case(cls, case_id: str, correlation_id: str) -> Case:
        if case_id.isdigit():
            case = Case.objects.filter(pk=int(case_id)).first()
            if case:
                return case

        case = Case.objects.filter(external_ref=case_id).first()
        if case:
            return case

        return Case.objects.create(
            external_ref=case_id,
            tenant_id="default",
            title=case_id,
            correlation_id=correlation_id,
            trace_id=correlation_id,
        )

    @classmethod
    def _to_domain_command(cls, record: AgentCommandRecord) -> AgentCommand:
        latest_response = record.responses.order_by("-created_at").first()
        return AgentCommand(
            command_id=record.command_id,
            case_id=record.case.external_ref or str(record.case_id),
            correlation_id=record.correlation_id,
            source_agent=record.source_agent,
            target_agent=record.target_agent,
            command_name=record.command_type,
            payload=record.input_payload,
            priority=cls._map_priority_from_record(record.priority),
            created_at=record.created_at,
            sent_at=record.started_at,
            completed_at=record.completed_at,
            status=cls._map_status_from_record(record.status),
            response=latest_response.output_payload if latest_response else None,
            error=record.last_error or None,
            retry_count=record.retry_count,
        )

    @classmethod
    def _map_status_from_record(cls, status: str) -> CommandStatus:
        mapping = {
            AgentCommandStatus.PENDING: CommandStatus.PENDING,
            AgentCommandStatus.DISPATCHED: CommandStatus.SENT,
            AgentCommandStatus.RUNNING: CommandStatus.PROCESSING,
            AgentCommandStatus.SUCCEEDED: CommandStatus.COMPLETED,
            AgentCommandStatus.TIMED_OUT: CommandStatus.TIMEOUT,
            AgentCommandStatus.FAILED: CommandStatus.FAILED,
            AgentCommandStatus.CANCELLED: CommandStatus.CANCELLED,
        }
        return mapping[status]

    @classmethod
    def _map_status_to_record(cls, status: CommandStatus) -> str:
        mapping = {
            CommandStatus.PENDING: AgentCommandStatus.PENDING,
            CommandStatus.SENT: AgentCommandStatus.DISPATCHED,
            CommandStatus.PROCESSING: AgentCommandStatus.RUNNING,
            CommandStatus.COMPLETED: AgentCommandStatus.SUCCEEDED,
            CommandStatus.TIMEOUT: AgentCommandStatus.TIMED_OUT,
            CommandStatus.FAILED: AgentCommandStatus.FAILED,
            CommandStatus.CANCELLED: AgentCommandStatus.CANCELLED,
        }
        return mapping[status]

    @classmethod
    def _map_priority(cls, priority: CommandPriority) -> str:
        mapping = {
            CommandPriority.LOW: Priority.LOW,
            CommandPriority.NORMAL: Priority.MEDIUM,
            CommandPriority.HIGH: Priority.HIGH,
            CommandPriority.CRITICAL: Priority.CRITICAL,
        }
        return mapping[priority]

    @classmethod
    def _map_priority_from_record(cls, priority: str) -> CommandPriority:
        mapping = {
            Priority.LOW: CommandPriority.LOW,
            Priority.MEDIUM: CommandPriority.NORMAL,
            Priority.HIGH: CommandPriority.HIGH,
            Priority.CRITICAL: CommandPriority.CRITICAL,
        }
        return mapping[priority]

    @classmethod
    def _build_idempotency_key(
        cls,
        case_id: str,
        source_agent: str,
        target_agent: str,
        command_name: str,
        payload: Dict[str, Any],
    ) -> str:
        base = json.dumps(
            {
                "case_id": case_id,
                "source_agent": source_agent,
                "target_agent": target_agent,
                "command_name": command_name,
                "payload": payload,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]

    @classmethod
    def _build_loop_signature(
        cls,
        tenant_id: str,
        case_id: str,
        source_agent: str,
        target_agent: str,
        command_name: str,
        payload: Dict[str, Any],
    ) -> str:
        raw = json.dumps(
            {
                "tenant_id": tenant_id,
                "case_id": case_id,
                "source_agent": source_agent,
                "target_agent": target_agent,
                "command_name": command_name,
                "payload": payload,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    @classmethod
    def _compute_jitter(cls, seed: str) -> int:
        return int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % 5
    
    @classmethod
    async def _emit_command_completed_event(cls, command: AgentCommand):
        """Emite evento de comando completado."""
        event = {
            "event_type": "agent.command.completed",
            "source": "inter_agent_bus",
            "payload": command.to_dict()
        }
        logger.info(f"Evento emitido: {event['event_type']}")
    
    @classmethod
    async def _emit_command_failed_event(cls, command: AgentCommand):
        """Emite evento de falha do comando."""
        event = {
            "event_type": "agent.command.failed",
            "source": "inter_agent_bus",
            "payload": command.to_dict()
        }
        logger.warning(f"Evento emitido: {event['event_type']}")


# =============================================================================
# CONTRATOS PADRÃO
# =============================================================================

def initialize_default_contracts():
    """Inicializa contratos padrão entre agentes."""
    
    # Intake -> SDR: Qualifique este lead
    intake_to_sdr = CommandContract(
        command_name="qualify_lead",
        source_agent="intake",
        target_agent="sdr",
        input_schema={
            "type": "object",
            "properties": {
                "lead_id": {"type": "string"},
                "lead_data": {"type": "object"},
                "context": {"type": "object"}
            },
            "required": ["lead_id", "lead_data"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "qualified": {"type": "boolean"},
                "decision_maker": {"type": "object"},
                "next_action": {"type": "string"}
            },
            "required": ["qualified", "next_action"]
        },
        timeout_seconds=60,
        max_retries=2
    )
    InterAgentBus.register_contract(intake_to_sdr)
    
    # SDR -> Sales: Envie proposta
    sdr_to_sales = CommandContract(
        command_name="generate_proposal",
        source_agent="sdr",
        target_agent="sales",
        input_schema={
            "type": "object",
            "properties": {
                "opportunity_id": {"type": "string"},
                "client_profile": {"type": "object"},
                "docai_analysis": {"type": "object"}
            },
            "required": ["opportunity_id"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string"},
                "proposal_value": {"type": "number"},
                "document_url": {"type": "string"}
            },
            "required": ["proposal_id"]
        },
        timeout_seconds=120,
        max_retries=2,
        requires_approval=True
    )
    InterAgentBus.register_contract(sdr_to_sales)
    
    # Sales -> Intake: Follow-up
    sales_to_intake = CommandContract(
        command_name="schedule_followup",
        source_agent="sales",
        target_agent="intake",
        input_schema={
            "type": "object",
            "properties": {
                "lead_id": {"type": "string"},
                "reason": {"type": "string"},
                "next_contact": {"type": "string"}
            },
            "required": ["lead_id", "next_contact"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "scheduled": {"type": "boolean"},
                "contact_at": {"type": "string"}
            },
            "required": ["scheduled"]
        },
        timeout_seconds=30
    )
    InterAgentBus.register_contract(sales_to_intake)
    
    # Any -> DocAI: Analise documento
    to_docai = CommandContract(
        command_name="analyze_document",
        source_agent="*",  # Qualquer um pode chamar
        target_agent="docai_operator",
        input_schema={
            "type": "object",
            "properties": {
                "document_path": {"type": "string"},
                "document_type": {"type": "string"},
                "case_id": {"type": "string"}
            },
            "required": ["document_path", "case_id"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "analysis_id": {"type": "string"},
                "status": {"type": "string"},
                "confidence": {"type": "number"}
            },
            "required": ["analysis_id", "status"]
        },
        timeout_seconds=300,  # DocAI pode ser lento
        max_retries=1
    )
    InterAgentBus.register_contract(to_docai)


# Inicializa contratos padrão
initialize_default_contracts()
