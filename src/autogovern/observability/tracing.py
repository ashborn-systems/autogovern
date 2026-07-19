"""OpenTelemetry trace export for pipeline stages and LLM calls.

Off by default. When enabled via ``config.observability.tracing: true`` and
the OTel packages are installed (``pip install autogovern[tracing]``), spans
emit to whatever ``OTEL_EXPORTER_OTLP_ENDPOINT`` points at.

Nothing leaves the machine unless the user configures a destination. When
tracing is disabled (the default), the OTel SDK is never imported and this
module's methods are no-ops.

The span tree mirrors the pipeline::

    trace: generate
    ├── span: normalise (label, used_llm, fallback)
    ├── span: generate.system-card (model, tokens)
    ├── span: generate.risk-assessment (model, tokens)
    └── span: generate.oversight (model, tokens)
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from autogovern.models import Config

# Module-level tracer. None when tracing is disabled or OTel is not installed.
_tracer: Any = None
_enabled: bool = False


def init_tracing(config: Config) -> None:
    """Initialise OTel tracing if enabled in config and packages are installed.

    Called once at the start of a command. If tracing is disabled (the
    default) or the OTel packages are not installed, this is a no-op and
    all subsequent span operations become no-ops.
    """
    global _tracer, _enabled

    if not config.observability.tracing:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        # Tracing enabled in config but OTel not installed. Silently
        # degrade — the user opted in, but we don't crash over a missing
        # optional dependency.
        return

    _enabled = True

    resource = Resource.create(
        {
            "service.name": "autogovern",
            "service.version": _tool_version(),
        }
    )
    provider = TracerProvider(resource=resource)

    # Only set up the OTLP exporter when an endpoint is configured.
    # Without an endpoint, spans are created but have nowhere to go.
    import os

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        except ImportError:
            pass

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("autogovern")


@contextmanager
def span(
    name: str,
    *,
    attributes: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """Emit a traced span, or a no-op context manager when tracing is off.

    Usage::

        with tracing.span("generate.system-card", attributes={"model": "claude-3"}):
            body = provider.chat(messages, label="system-card")
    """
    if not _enabled or _tracer is None:
        yield None
        return

    with _tracer.start_as_current_span(name) as s:
        if attributes:
            for key, value in attributes.items():
                s.set_attribute(key, value)
        start = time.time()
        yield s
        s.set_attribute("duration_ms", (time.time() - start) * 1000)


def record_llm_call(
    *,
    label: str,
    model: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
) -> None:
    """Record LLM call attributes on the current span (if any)."""
    if not _enabled or _tracer is None:
        return

    current = _tracer.get_current_span()
    if current is None:
        return

    current.set_attribute("llm.label", label)
    current.set_attribute("llm.model", model)
    if prompt_tokens is not None:
        current.set_attribute("llm.tokens.prompt", prompt_tokens)
    if completion_tokens is not None:
        current.set_attribute("llm.tokens.completion", completion_tokens)
    if total_tokens is not None:
        current.set_attribute("llm.tokens.total", total_tokens)


def is_enabled() -> bool:
    """True when tracing is active (packages installed and config enabled)."""
    return _enabled


def shutdown() -> None:
    """Flush and shut down the tracer provider, if active."""
    global _tracer, _enabled

    if not _enabled:
        return

    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
    except Exception:
        pass
    finally:
        _tracer = None
        _enabled = False


def _tool_version() -> str:
    try:
        from importlib.metadata import version

        return version("autogovern")
    except Exception:  # pragma: no cover
        return "0.0.0+dev"


__all__ = ["init_tracing", "is_enabled", "record_llm_call", "shutdown", "span"]
