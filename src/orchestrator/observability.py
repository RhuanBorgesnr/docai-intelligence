"""
Observabilidade - Tracing distribuído, métricas e logging estruturado.

Responsabilidades:
- Rastreamento distribuído (trace_id, span_id)
- Coleta de métricas por agente
- Latência por componente
- Taxa de erro
- Cache hit rate
- Falhas por tipo
"""

import logging
import time
from typing import Any, Dict, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import json

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Tipos de métricas."""
    COUNTER = "counter"  # Incrementa (eventos, erros)
    GAUGE = "gauge"  # Valor instantâneo (queue size, memory)
    HISTOGRAM = "histogram"  # Distribuição (latência, tamanho)
    TIMER = "timer"  # Duração (execution time)


@dataclass
class Span:
    """Representa um span em um trace distribuído."""
    
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    
    operation_name: str
    component: str  # agent_runner, approval_gateway, docai_adapter, etc
    
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    
    status: str = "started"  # started, completed, failed
    error_message: Optional[str] = None
    
    # Dados customizados
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: list = field(default_factory=list)
    
    @property
    def duration_ms(self) -> float:
        """Duração em milliseconds."""
        end = self.end_time or datetime.utcnow()
        return (end - self.start_time).total_seconds() * 1000
    
    def add_tag(self, key: str, value: Any):
        """Adiciona tag ao span."""
        self.tags[key] = value
    
    def add_log(self, message: str, level: str = "info"):
        """Adiciona log estruturado ao span."""
        self.logs.append({
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message
        })
    
    def complete(self, status: str = "completed", error: Optional[str] = None):
        """Marca span como completo."""
        self.end_time = datetime.utcnow()
        self.status = status
        if error:
            self.error_message = error
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "operation_name": self.operation_name,
            "component": self.component,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error_message": self.error_message,
            "tags": self.tags,
            "logs": self.logs
        }


@dataclass
class Metric:
    """Uma métrica individual."""
    
    metric_type: MetricType
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "metric_type": self.metric_type.value,
            "name": self.name,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp.isoformat()
        }


class Tracer:
    """Sistema de tracing distribuído."""
    
    # Armazena spans
    _spans: Dict[str, Span] = {}
    _span_counter: int = 0
    
    # Rastreia span atual por thread/context
    _current_trace: Dict[str, str] = {}  # {context_id: trace_id}
    _current_span: Dict[str, str] = {}   # {context_id: span_id}
    
    @classmethod
    def start_trace(cls, trace_id: str) -> str:
        """Inicia um novo trace."""
        # Em produção, usaria contexto por thread/async
        context_id = "default"
        cls._current_trace[context_id] = trace_id
        logger.debug(f"Trace iniciado: {trace_id}")
        return trace_id
    
    @classmethod
    def start_span(
        cls,
        operation_name: str,
        component: str,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None
    ) -> Span:
        """Inicia um novo span."""
        
        context_id = "default"
        
        # Recupera trace_id do contexto
        if not trace_id:
            trace_id = cls._current_trace.get(context_id, "no_trace")
        
        # Recupera parent se não fornecido
        if not parent_span_id:
            parent_span_id = cls._current_span.get(context_id)
        
        # Gera span_id
        cls._span_counter += 1
        span_id = f"span_{cls._span_counter}"
        
        # Cria span
        span = Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            component=component,
            tags=tags or {}
        )
        
        # Persiste
        cls._spans[span_id] = span
        cls._current_span[context_id] = span_id
        
        logger.debug(
            f"Span iniciado: {span_id} "
            f"(trace={trace_id}, component={component})"
        )
        
        return span
    
    @classmethod
    def end_span(
        cls,
        span_id: str,
        status: str = "completed",
        error: Optional[str] = None
    ) -> Optional[Span]:
        """Encerra um span."""
        
        span = cls._spans.get(span_id)
        if not span:
            logger.warning(f"Span não encontrado: {span_id}")
            return None
        
        span.complete(status=status, error=error)
        
        logger.debug(
            f"Span encerrado: {span_id} "
            f"(status={status}, duration={span.duration_ms:.2f}ms)"
        )
        
        return span
    
    @classmethod
    def get_trace(cls, trace_id: str) -> Dict[str, Any]:
        """Recupera todos os spans de um trace."""
        
        spans = [
            span for span in cls._spans.values()
            if span.trace_id == trace_id
        ]
        
        # Ordena por start_time
        spans = sorted(spans, key=lambda s: s.start_time)
        
        return {
            "trace_id": trace_id,
            "span_count": len(spans),
            "total_duration_ms": sum(s.duration_ms for s in spans),
            "spans": [s.to_dict() for s in spans]
        }
    
    @classmethod
    def get_span(cls, span_id: str) -> Optional[Span]:
        """Recupera um span específico."""
        return cls._spans.get(span_id)


class MetricsCollector:
    """Coleta e agrega métricas do sistema."""
    
    _metrics: Dict[str, list] = {}  # {metric_name: [Metric]}
    
    @classmethod
    def record_metric(
        cls,
        metric_type: MetricType,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ) -> Metric:
        """Registra uma métrica."""
        
        metric = Metric(
            metric_type=metric_type,
            name=name,
            value=value,
            labels=labels or {}
        )
        
        if name not in cls._metrics:
            cls._metrics[name] = []
        
        cls._metrics[name].append(metric)
        
        # Mantém apenas últimas 1000 métricas por nome
        if len(cls._metrics[name]) > 1000:
            cls._metrics[name] = cls._metrics[name][-1000:]
        
        return metric
    
    @classmethod
    def increment_counter(
        cls,
        name: str,
        amount: float = 1.0,
        labels: Optional[Dict[str, str]] = None
    ):
        """Incrementa um contador."""
        cls.record_metric(
            MetricType.COUNTER,
            name,
            amount,
            labels=labels
        )
    
    @classmethod
    def record_gauge(
        cls,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ):
        """Registra um gauge (valor instantâneo)."""
        cls.record_metric(
            MetricType.GAUGE,
            name,
            value,
            labels=labels
        )
    
    @classmethod
    def record_histogram(
        cls,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ):
        """Registra um valor em histograma (ex: latência)."""
        cls.record_metric(
            MetricType.HISTOGRAM,
            name,
            value,
            labels=labels
        )
    
    @classmethod
    def get_metrics_summary(cls) -> Dict[str, Any]:
        """Retorna resumo de métricas coletadas."""
        
        summary = {}
        
        for metric_name, metrics in cls._metrics.items():
            if not metrics:
                continue
            
            values = [m.value for m in metrics]
            
            summary[metric_name] = {
                "count": len(values),
                "sum": sum(values),
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "latest": values[-1] if values else 0
            }
        
        return summary
    
    @classmethod
    def get_metric_timeseries(
        cls,
        metric_name: str,
        limit: int = 100
    ) -> list:
        """Retorna série temporal de uma métrica."""
        
        metrics = cls._metrics.get(metric_name, [])
        
        # Retorna últimas N
        metrics = metrics[-limit:]
        
        return [m.to_dict() for m in metrics]


class ObservabilityContext:
    """Context manager para rastreamento automático."""
    
    def __init__(
        self,
        operation_name: str,
        component: str,
        trace_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None
    ):
        self.operation_name = operation_name
        self.component = component
        self.trace_id = trace_id
        self.tags = tags or {}
        self.span: Optional[Span] = None
    
    def __enter__(self) -> Span:
        """Inicia tracing ao entrar no contexto."""
        
        self.span = Tracer.start_span(
            operation_name=self.operation_name,
            component=self.component,
            trace_id=self.trace_id,
            tags=self.tags
        )
        
        return self.span
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Encerra tracing ao sair do contexto."""
        
        if not self.span:
            return
        
        if exc_type:
            Tracer.end_span(
                self.span.span_id,
                status="failed",
                error=str(exc_val)
            )
            
            MetricsCollector.increment_counter(
                f"{self.component}.errors",
                labels={"error_type": exc_type.__name__}
            )
        else:
            Tracer.end_span(self.span.span_id, status="completed")
        
        # Registra latência
        MetricsCollector.record_histogram(
            f"{self.component}.latency_ms",
            self.span.duration_ms,
            labels={"operation": self.operation_name}
        )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_structured_log(
    level: str,
    message: str,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Cria um log estruturado."""
    
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "level": level,
        "message": message,
        "trace_id": trace_id,
        "span_id": span_id,
    }
    
    if context:
        log_entry["context"] = context
    
    return log_entry


def log_structured(
    level: str,
    message: str,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
):
    """Loga estruturado em JSON."""
    
    log_entry = create_structured_log(
        level=level,
        message=message,
        trace_id=trace_id,
        span_id=span_id,
        context=context
    )
    
    # Formata para logging
    if level == "error":
        logger.error(json.dumps(log_entry))
    elif level == "warning":
        logger.warning(json.dumps(log_entry))
    elif level == "info":
        logger.info(json.dumps(log_entry))
    else:
        logger.debug(json.dumps(log_entry))
