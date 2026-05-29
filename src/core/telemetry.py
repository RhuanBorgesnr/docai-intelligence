"""
Telemetry bootstrap — OpenTelemetry with graceful no-op fallback.

Design goals:
- Works with zero extra infra (no OTLP collector required in dev/test).
- When OTEL_EXPORTER_OTLP_ENDPOINT is set, emits real OTLP traces.
- Fallback to a simple structlog/logging-based tracer otherwise.
- Propagates correlation_id, causation_id, tenant_id, case_id through
  contextvars so Celery workers and Django views share the same trace context.
- All instrumentation is additive: removing this module changes nothing else.

Usage:
    from core.telemetry import get_tracer, record_event, extract_context, inject_context

    with get_tracer().start_as_current_span("my.operation") as span:
        span.set_attribute("case_id", case_id)
        ...

    # Propagate across Celery task boundary:
    carrier = inject_context()           # dict to pass as task kwarg
    extract_context(carrier)             # call at start of task
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)

# ── context vars (always available, no otel required) ─────────────────────────
_cv_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
_cv_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_cv_causation_id: ContextVar[str] = ContextVar("causation_id", default="")
_cv_tenant_id: ContextVar[str] = ContextVar("tenant_id", default="default")
_cv_case_id: ContextVar[str] = ContextVar("case_id", default="")
_cv_span_name: ContextVar[str] = ContextVar("span_name", default="")


def set_context(
    correlation_id: str = "",
    trace_id: str = "",
    causation_id: str = "",
    tenant_id: str = "default",
    case_id: str = "",
) -> None:
    """Seed context vars at the entry point of a request / task."""
    if correlation_id:
        _cv_correlation_id.set(correlation_id)
    if trace_id:
        _cv_trace_id.set(trace_id)
    if causation_id:
        _cv_causation_id.set(causation_id)
    if tenant_id:
        _cv_tenant_id.set(tenant_id)
    if case_id:
        _cv_case_id.set(case_id)


def get_context() -> dict:
    """Return the current trace context as a plain dict."""
    return {
        "correlation_id": _cv_correlation_id.get(),
        "trace_id": _cv_trace_id.get(),
        "causation_id": _cv_causation_id.get(),
        "tenant_id": _cv_tenant_id.get(),
        "case_id": _cv_case_id.get(),
    }


def inject_context() -> dict:
    """Serialize context to a carrier dict for passing across task boundaries."""
    return get_context()


def extract_context(carrier: dict) -> None:
    """Restore context from a carrier dict (e.g. at the start of a Celery task)."""
    set_context(**{k: v for k, v in carrier.items() if k in {
        "correlation_id", "trace_id", "causation_id", "tenant_id", "case_id"
    }})


# ── otel bootstrap ─────────────────────────────────────────────────────────────

_OTEL_AVAILABLE = False
_tracer = None

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    _otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    _service_name = os.environ.get("OTEL_SERVICE_NAME", "plataforma-inteligencia")

    resource = Resource.create({"service.name": _service_name})
    provider = TracerProvider(resource=resource)

    if _otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=_otlp_endpoint))
            )
            logger.info("[telemetry] OTLP exporter → %s", _otlp_endpoint)
        except ImportError:
            logger.warning(
                "[telemetry] opentelemetry-exporter-otlp not installed; "
                "falling back to console exporter"
            )
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        # In development / CI: log-based exporter (very low noise)
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(_service_name)
    _OTEL_AVAILABLE = True
    logger.info("[telemetry] OpenTelemetry initialized (service=%s)", _service_name)

except ImportError:
    logger.info(
        "[telemetry] opentelemetry-sdk not installed; using no-op tracer. "
        "Install opentelemetry-sdk for real traces."
    )


# ── no-op fallback ─────────────────────────────────────────────────────────────

class _NoopSpan:
    """Minimal span that logs structured events but does no real tracing."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._attrs: dict = {}

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: ANN001
        self._attrs[key] = value

    def record_exception(self, exc: Exception) -> None:  # noqa: ANN001
        logger.exception("[span:%s] exception", self._name, exc_info=exc)

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> "_NoopSpan":
        ctx = get_context()
        logger.debug(
            "[span] start name=%s correlation=%s trace=%s tenant=%s",
            self._name,
            ctx["correlation_id"],
            ctx["trace_id"],
            ctx["tenant_id"],
        )
        return self

    def __exit__(self, *args: Any) -> None:
        logger.debug("[span] end name=%s attrs=%s", self._name, self._attrs)


class _NoopTracer:
    @contextmanager  # type: ignore[misc]
    def start_as_current_span(
        self, name: str, **_kwargs: Any
    ) -> Generator["_NoopSpan", None, None]:
        span = _NoopSpan(name)
        with span:
            yield span


# ── public API ────────────────────────────────────────────────────────────────

def get_tracer() -> Any:
    """Return the active tracer (OTel or no-op)."""
    if _OTEL_AVAILABLE and _tracer is not None:
        return _tracer
    return _NoopTracer()


def record_event(name: str, attributes: Optional[dict] = None) -> None:
    """Log a named event with the current trace context."""
    ctx = get_context()
    merged = {**ctx, **(attributes or {})}
    logger.info("[event] %s attrs=%s", name, merged)


def span_attributes_from_context() -> dict:
    """Build a set of span attributes from current context vars."""
    ctx = get_context()
    return {
        "correlation_id": ctx["correlation_id"],
        "trace_id": ctx["trace_id"],
        "tenant_id": ctx["tenant_id"],
        "case_id": ctx["case_id"],
    }
