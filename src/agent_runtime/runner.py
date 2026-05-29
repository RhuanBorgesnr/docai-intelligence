"""
Agent Runner - Execução padronizada e observável de agentes LLM.

Responsabilidades:
- Executar comandos de agentes
- Integrar com LLMs (OpenAI, Claude, etc)
- Validar outputs contra schemas
- Implementar retries e timeouts
- Rastrear execução e métricas
- Armazenar resultados
- Lidar com fallbacks
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import hashlib

from .prompt_registry import (
    PromptRegistry, AgentType, OutputSchema, PromptPolicy
)

logger = logging.getLogger(__name__)


class AgentExecutionStatus(str, Enum):
    """Status da execução de um agente."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SCHEMA_INVALID = "schema_invalid"
    RETRY = "retry"
    FALLBACK = "fallback"


@dataclass
class ExecutionMetrics:
    """Métricas de execução de um agente."""
    
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0
    llm_latency_ms: float = 0.0
    validation_latency_ms: float = 0.0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    retry_count: int = 0
    cache_hit: bool = False
    
    @property
    def total_latency_ms(self) -> float:
        """Latência total da execução."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "llm_latency_ms": self.llm_latency_ms,
            "validation_latency_ms": self.validation_latency_ms,
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "retry_count": self.retry_count,
            "cache_hit": self.cache_hit,
            "total_latency_ms": self.total_latency_ms
        }


@dataclass
class AgentExecutionResult:
    """Resultado da execução de um agente."""
    
    execution_id: str
    agent_type: AgentType
    status: AgentExecutionStatus
    output: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    error: Optional[str] = None
    validation_errors: list = field(default_factory=list)
    metrics: Optional[ExecutionMetrics] = None
    cache_hit: bool = False
    
    def is_success(self) -> bool:
        """Indica se a execução foi bem-sucedida."""
        return self.status == AgentExecutionStatus.SUCCESS
    
    def is_retryable(self) -> bool:
        """Indica se o erro é retentável."""
        return self.status in [
            AgentExecutionStatus.TIMEOUT,
            AgentExecutionStatus.FAILED,
            AgentExecutionStatus.RETRY
        ]
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "execution_id": self.execution_id,
            "agent_type": self.agent_type.value,
            "status": self.status.value,
            "output": self.output,
            "confidence": self.confidence,
            "error": self.error,
            "validation_errors": self.validation_errors,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "cache_hit": self.cache_hit
        }


class LLMExecutor:
    """Abstração para executar chamadas a LLMs.
    
    Providers suportados:
    - "groq" (padrão local — gratuito, Llama 3.3 70B)
    - "openai" (GPT-4)
    - "anthropic" (Claude)
    
    Quando nenhum provider está configurado, retorna erro explícito.
    Não há mock silencioso.
    """
    
    def __init__(self, provider: str = "groq"):
        """
        Args:
            provider: "groq", "openai", "anthropic"
        """
        self.provider = provider
        self.model = ""
        self.client = None
        self._provider_ready = False
        self._init_error = ""
        self._initialize_client()
    
    def _initialize_client(self):
        """Inicializa cliente do LLM."""
        if self.provider == "groq":
            try:
                from django.conf import settings as django_settings
                api_key = getattr(django_settings, 'GROQ_API_KEY', '') or os.environ.get('GROQ_API_KEY', '')
                if api_key:
                    self.client = {"api_key": api_key}  # Groq usa requests direto
                    self.model = "llama-3.3-70b-versatile"
                    self._provider_ready = True
                    logger.info("LLM provider GROQ inicializado (model=%s)", self.model)
                else:
                    self._init_error = "GROQ_API_KEY não configurada. Defina no .env ou variável de ambiente."
                    logger.warning(self._init_error)
            except Exception as e:
                self._init_error = f"Erro ao inicializar Groq: {e}"
                logger.warning(self._init_error)

        elif self.provider == "openai":
            try:
                import openai
                api_key = os.environ.get('OPENAI_API_KEY', '')
                if not api_key:
                    self._init_error = "OPENAI_API_KEY não configurada."
                    logger.warning(self._init_error)
                    return
                self.client = openai.OpenAI(api_key=api_key)
                self.model = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
                self._provider_ready = True
                logger.info("LLM provider OpenAI inicializado (model=%s)", self.model)
            except ImportError:
                self._init_error = "Pacote openai não instalado."
                logger.warning(self._init_error)
            except Exception as e:
                self._init_error = f"Erro ao inicializar OpenAI: {e}"
                logger.warning(self._init_error)
        
        elif self.provider == "anthropic":
            try:
                import anthropic
                api_key = os.environ.get('ANTHROPIC_API_KEY', '')
                if not api_key:
                    self._init_error = "ANTHROPIC_API_KEY não configurada."
                    logger.warning(self._init_error)
                    return
                self.client = anthropic.Anthropic(api_key=api_key)
                self.model = "claude-3-5-sonnet-20241022"
                self._provider_ready = True
                logger.info("LLM provider Anthropic inicializado (model=%s)", self.model)
            except ImportError:
                self._init_error = "Pacote anthropic não instalado."
                logger.warning(self._init_error)
            except Exception as e:
                self._init_error = f"Erro ao inicializar Anthropic: {e}"
                logger.warning(self._init_error)
        else:
            self._init_error = f"Provider desconhecido: {self.provider}"
            logger.warning(self._init_error)
    
    @property
    def is_ready(self) -> bool:
        return self._provider_ready
    
    async def execute_prompt(
        self,
        system_prompt: str,
        user_message: str,
        output_schema: Optional[OutputSchema] = None,
        policy: Optional[PromptPolicy] = None,
        timeout_seconds: int = 30
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Executa um prompt no LLM.
        
        Sem mock silencioso: se o provider não está pronto, retorna erro explícito.
        """
        
        if not self._provider_ready:
            logger.error("LLM provider '%s' não disponível: %s", self.provider, self._init_error)
            return None, {
                "error": f"provider_not_ready: {self._init_error}",
                "model": "none",
                "tokens_used": 0,
                "provider": self.provider,
                "provider_ready": False,
            }
        
        policy = policy or PromptPolicy()
        
        try:
            start_time = time.time()
            
            if self.provider == "groq":
                return await self._execute_groq(system_prompt, user_message, policy, timeout_seconds)
            
            elif self.provider == "openai":
                return await self._execute_openai(system_prompt, user_message, policy, timeout_seconds)
            
            elif self.provider == "anthropic":
                return await self._execute_anthropic(system_prompt, user_message, policy, timeout_seconds)
        
        except asyncio.TimeoutError:
            logger.error(f"LLM timeout after {timeout_seconds}s")
            return None, {"error": "timeout", "provider": self.provider}
        
        except Exception as e:
            logger.error(f"LLM execution error: {str(e)}", exc_info=True)
            return None, {"error": str(e), "provider": self.provider}
    
    async def _execute_groq(
        self, system_prompt: str, user_message: str, policy: PromptPolicy, timeout_seconds: int
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """Executa no Groq (Llama 3.3 70B) via HTTP."""
        import requests as http_requests
        
        start_time = time.time()
        api_key = self.client["api_key"]
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        # Groq json_object mode requires the prompt to mention JSON
        _sys = system_prompt
        if "json" not in _sys.lower():
            _sys += "\n\nResponda SEMPRE em formato JSON válido."
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _sys},
                {"role": "user", "content": user_message},
            ],
            "temperature": policy.temperature,
            "max_tokens": min(policy.max_tokens, 4096),
            "response_format": {"type": "json_object"},
        }
        
        # Run HTTP call in thread pool to not block async loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: http_requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
        )
        
        elapsed = time.time() - start_time
        
        if not response.ok:
            logger.error("Groq API error %s: %s", response.status_code, response.text[:500])
        response.raise_for_status()
        data = response.json()
        
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        
        try:
            output = json.loads(content)
        except json.JSONDecodeError:
            output = self._extract_json_from_text(content)
        
        return output, {
            "model": self.model,
            "tokens_used": usage.get("total_tokens", 0),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "llm_latency_ms": elapsed * 1000,
            "provider": "groq",
            "provider_ready": True,
        }
    
    async def _execute_openai(
        self, system_prompt: str, user_message: str, policy: PromptPolicy, timeout_seconds: int
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """Executa no OpenAI."""
        start_time = time.time()
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=policy.temperature,
            max_tokens=policy.max_tokens,
            top_p=policy.top_p,
            frequency_penalty=policy.frequency_penalty,
            presence_penalty=policy.presence_penalty,
            timeout=timeout_seconds
        )
        
        elapsed = time.time() - start_time
        content = response.choices[0].message.content
        
        try:
            output = json.loads(content)
        except json.JSONDecodeError:
            output = self._extract_json_from_text(content)
        
        return output, {
            "model": self.model,
            "tokens_used": response.usage.total_tokens if response.usage else 0,
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "llm_latency_ms": elapsed * 1000,
            "provider": "openai",
            "provider_ready": True,
        }
    
    async def _execute_anthropic(
        self, system_prompt: str, user_message: str, policy: PromptPolicy, timeout_seconds: int
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """Executa no Anthropic (Claude)."""
        start_time = time.time()
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=policy.max_tokens,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ],
            timeout=timeout_seconds
        )
        
        elapsed = time.time() - start_time
        content = response.content[0].text
        
        try:
            output = json.loads(content)
        except json.JSONDecodeError:
            output = self._extract_json_from_text(content)
        
        return output, {
            "model": self.model,
            "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "llm_latency_ms": elapsed * 1000,
            "provider": "anthropic",
            "provider_ready": True,
        }
    
    def _extract_json_from_text(self, text: str) -> Dict[str, Any]:
        """Tenta extrair JSON de texto não-estruturado."""
        import re
        
        # Tenta encontrar JSON entre chaves
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # Fallback: retorna como string simples
        return {"content": text}


class AgentRunner:
    """Motor de execução de agentes."""
    
    def __init__(self, llm_provider: str = "openai"):
        """
        Args:
            llm_provider: Provedor de LLM a usar
        """
        self.llm_executor = LLMExecutor(provider=llm_provider)
        self._execution_cache = {}  # {execution_hash: result}
    
    async def execute_agent_command(
        self,
        agent_type: AgentType,
        context: Dict[str, Any],
        correlation_id: str,
        use_cache: bool = True,
        retry_on_failure: bool = True
    ) -> AgentExecutionResult:
        """
        Executa um comando de agente.
        
        Args:
            agent_type: Tipo de agente
            context: Contexto para renderizar prompt
            correlation_id: ID para rastreamento
            use_cache: Usar cache de execuções anteriores
            retry_on_failure: Retry automático em falhas
        
        Returns:
            AgentExecutionResult com output e métricas
        """
        
        # Gera ID de execução único
        execution_id = self._generate_execution_id(agent_type, context)
        
        # Tenta cache
        if use_cache:
            cached_result = self._get_cached_result(execution_id)
            if cached_result:
                logger.info(f"Cache hit para execução {execution_id}")
                cached_result.cache_hit = True
                return cached_result
        
        # Recupera configurações do agente
        prompt_version = PromptRegistry.get_prompt(agent_type)
        policy = PromptRegistry.get_policy(agent_type)
        schema = PromptRegistry.get_schema(agent_type)
        
        if not prompt_version:
            return AgentExecutionResult(
                execution_id=execution_id,
                agent_type=agent_type,
                status=AgentExecutionStatus.FAILED,
                error=f"Nenhum prompt registrado para {agent_type.value}"
            )
        
        # Inicializa métricas
        metrics = ExecutionMetrics(start_time=datetime.now())
        
        logger.info(f"Iniciando execução do agente {agent_type.value} "
                   f"(correlation_id={correlation_id}, execution_id={execution_id})")
        
        # Loop de retry
        attempt = 0
        while attempt < (policy.max_retries if policy else 3):
            attempt += 1
            
            result = await self._execute_single_attempt(
                agent_type=agent_type,
                prompt_version=prompt_version,
                context=context,
                policy=policy,
                schema=schema,
                metrics=metrics,
                execution_id=execution_id,
                attempt=attempt
            )
            
            if result.is_success():
                # Cache result
                if use_cache:
                    self._cache_result(execution_id, result)
                
                metrics.end_time = datetime.now()
                
                # ── Cost tracking ─────────────────────────────────
                try:
                    from .cost_tracker import record_execution
                    output_preview = ""
                    if result.output and isinstance(result.output, dict):
                        output_preview = str(result.output)[:200]
                    record_execution(
                        execution_id=execution_id,
                        agent_type=agent_type.value,
                        provider=self.llm_executor.provider,
                        prompt_tokens=metrics.prompt_tokens,
                        completion_tokens=metrics.completion_tokens,
                        latency_ms=metrics.total_latency_ms,
                        llm_latency_ms=metrics.llm_latency_ms,
                        retry_count=metrics.retry_count,
                        cache_hit=metrics.cache_hit,
                        status=result.status.value,
                        output_summary=output_preview,
                        correlation_id=correlation_id,
                        trigger=context.get("_trigger", ""),
                        lead_id=context.get("_lead_id", ""),
                    )
                except Exception as e:
                    logger.warning("Cost tracking failed (non-blocking): %s", e)
                # ──────────────────────────────────────────────────

                # ── WebSocket broadcast ───────────────────────────
                try:
                    from orchestrator.ws_broadcasts import sync_broadcast_agent_status
                    sync_broadcast_agent_status(
                        agent_name=agent_type.value,
                        status="task_complete",
                        detail={
                            "execution_id": execution_id,
                            "correlation_id": correlation_id,
                            "latency_ms": metrics.total_latency_ms,
                            "tokens": metrics.total_tokens,
                        },
                    )
                except Exception:
                    pass  # best-effort
                # ──────────────────────────────────────────────────
                
                return result
            
            # Se é retentável e ainda temos tentativas, retry
            if result.is_retryable() and attempt < (policy.max_retries if policy else 3):
                wait_time = 2 ** (attempt - 1)  # Exponential backoff: 1s, 2s, 4s
                logger.warning(f"Tentativa {attempt} falhou para {agent_type.value}, "
                             f"retrying em {wait_time}s")
                await asyncio.sleep(wait_time)
                metrics.retry_count += 1
                continue
            
            # Falha definitiva
            metrics.end_time = datetime.now()
            return result
        
        # Esgotou retries
        metrics.end_time = datetime.now()
        return AgentExecutionResult(
            execution_id=execution_id,
            agent_type=agent_type,
            status=AgentExecutionStatus.FAILED,
            error=f"Falha após {attempt} tentativas",
            metrics=metrics
        )
    
    async def _execute_single_attempt(
        self,
        agent_type: AgentType,
        prompt_version,
        context: Dict[str, Any],
        policy: Optional[PromptPolicy],
        schema: Optional[OutputSchema],
        metrics: ExecutionMetrics,
        execution_id: str,
        attempt: int
    ) -> AgentExecutionResult:
        """Executa uma única tentativa."""
        
        try:
            # Renderiza prompt com contexto
            system_prompt = prompt_version.content
            user_message = json.dumps(context, ensure_ascii=False)
            
            # Se tem variáveis, tenta injetar
            if prompt_version.variables and isinstance(context, dict):
                try:
                    rendered_system = prompt_version.render(context)
                    system_prompt = rendered_system
                except ValueError as e:
                    # Algumas variáveis podem estar faltando, isso é OK
                    logger.debug(f"Variáveis incompletas no prompt: {str(e)}")
                    pass
            
            # Timeout do policy ou padrão
            timeout = policy.timeout_seconds if policy else 30
            
            # Executa no LLM
            output, llm_metadata = await self.llm_executor.execute_prompt(
                system_prompt=system_prompt,
                user_message=user_message,
                output_schema=schema,
                policy=policy,
                timeout_seconds=timeout
            )
            
            # Atualiza métricas
            metrics.llm_latency_ms = llm_metadata.get("llm_latency_ms", 0)
            metrics.total_tokens = llm_metadata.get("tokens_used", 0)
            metrics.prompt_tokens = llm_metadata.get("prompt_tokens", 0)
            metrics.completion_tokens = llm_metadata.get("completion_tokens", 0)
            
            # Trata erro no LLM
            if llm_metadata.get("error"):
                if llm_metadata.get("error") == "timeout":
                    return AgentExecutionResult(
                        execution_id=execution_id,
                        agent_type=agent_type,
                        status=AgentExecutionStatus.TIMEOUT,
                        error=f"LLM timeout na tentativa {attempt}",
                        metrics=metrics
                    )
                else:
                    return AgentExecutionResult(
                        execution_id=execution_id,
                        agent_type=agent_type,
                        status=AgentExecutionStatus.FAILED,
                        error=f"LLM error: {llm_metadata.get('error')}",
                        metrics=metrics
                    )
            
            if not output:
                return AgentExecutionResult(
                    execution_id=execution_id,
                    agent_type=agent_type,
                    status=AgentExecutionStatus.FAILED,
                    error="LLM retornou output vazio",
                    metrics=metrics
                )
            
            # Valida output contra schema
            if schema:
                val_start = time.time()
                is_valid, error_msg = schema.validate(output)
                metrics.validation_latency_ms = (time.time() - val_start) * 1000
                
                if not is_valid:
                    logger.error(f"Schema validation failed: {error_msg}")
                    return AgentExecutionResult(
                        execution_id=execution_id,
                        agent_type=agent_type,
                        status=AgentExecutionStatus.SCHEMA_INVALID,
                        output=output,
                        error=error_msg,
                        validation_errors=[error_msg],
                        metrics=metrics
                    )
            
            # Extrai confidence se presente
            confidence = output.get("confidence", 0.8) if isinstance(output, dict) else 0.8
            
            # Sucesso!
            return AgentExecutionResult(
                execution_id=execution_id,
                agent_type=agent_type,
                status=AgentExecutionStatus.SUCCESS,
                output=output,
                confidence=confidence,
                metrics=metrics
            )
        
        except Exception as e:
            logger.error(f"Execução falhou: {str(e)}", exc_info=True)
            return AgentExecutionResult(
                execution_id=execution_id,
                agent_type=agent_type,
                status=AgentExecutionStatus.FAILED,
                error=f"Exceção: {str(e)}",
                metrics=metrics
            )
    
    def _generate_execution_id(self, agent_type: AgentType, context: Dict[str, Any]) -> str:
        """Gera ID único para uma execução."""
        context_str = json.dumps(context, sort_keys=True, default=str)
        hash_input = f"{agent_type.value}:{context_str}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    def _get_cached_result(self, execution_id: str) -> Optional[AgentExecutionResult]:
        """Recupera resultado do cache."""
        return self._execution_cache.get(execution_id)
    
    def _cache_result(self, execution_id: str, result: AgentExecutionResult):
        """Cacheia resultado de execução."""
        # Limpa cache antigo se ficar muito grande
        if len(self._execution_cache) > 1000:
            # Mantém apenas 100 itens mais recentes
            keys_to_keep = list(self._execution_cache.keys())[-100:]
            self._execution_cache = {k: self._execution_cache[k] for k in keys_to_keep}
        
        self._execution_cache[execution_id] = result
    
    def clear_cache(self):
        """Limpa cache de execuções."""
        self._execution_cache.clear()
