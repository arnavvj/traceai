"""
TraceAI — Chrome DevTools for AI agents.

Quick start:

    from traceai import tracer

    @tracer.trace
    def my_agent(prompt: str) -> str:
        with tracer.span("llm-call", kind="llm_call") as span:
            span.set_input({"prompt": prompt})
            result = call_llm(prompt)
            span.set_output({"response": result})
        return result

Auto-instrumentation (OpenAI):

    import traceai
    traceai.instrument("openai")
"""

from traceai.models import ErrorDetail, Span, SpanKind, SpanStatus, Trace
from traceai.storage import TraceStore

__version__ = "0.1.0"

__all__ = [
    # Core models
    "Span",
    "Trace",
    "SpanKind",
    "SpanStatus",
    "ErrorDetail",
    # Storage
    "TraceStore",
    # Tracer singleton — imported lazily below to avoid circular imports
    "tracer",
    # Auto-instrumentation
    "instrument",
    "__version__",
]


def instrument(provider: str) -> None:
    """
    Auto-instrument a known LLM provider SDK.

    Supported providers: "openai", "anthropic"

    Example:
        import traceai
        traceai.instrument("openai")
    """
    from traceai.integrations import instrument as _instrument

    _instrument(provider)


# Import tracer last — it depends on models and storage being importable first.
from traceai.tracer import Tracer  # noqa: E402

tracer: Tracer = Tracer()
