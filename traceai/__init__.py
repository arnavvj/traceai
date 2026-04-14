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

__version__ = "0.5.0"

__all__ = [
    # Core models
    "Span",
    "Trace",
    "SpanKind",
    "SpanStatus",
    "ErrorDetail",
    # Storage
    "TraceStore",
    # Tracer and SpanContext — imported lazily below to avoid circular imports
    "tracer",
    "Tracer",
    "SpanContext",
    # Auto-instrumentation
    "instrument",
    # Configuration
    "configure",
    # Experiments
    "experiment",
    "__version__",
]


def configure(sample_rate: float = 1.0) -> None:
    """
    Configure global tracer settings.

    Args:
        sample_rate: Fraction of traces to capture (0.0–1.0). Defaults to 1.0
            (capture everything). Set to 0.5 to capture roughly half of all
            traces, 0.0 to disable tracing entirely.

    Raises:
        ValueError: If ``sample_rate`` is outside [0.0, 1.0].

    Example:
        import traceai
        traceai.configure(sample_rate=0.25)   # capture 25 % of traces
    """
    if not 0.0 <= sample_rate <= 1.0:
        raise ValueError(f"sample_rate must be between 0.0 and 1.0, got {sample_rate}")
    tracer._sample_rate = sample_rate


def experiment(name: str) -> "_ExperimentCM":
    """
    Context manager that groups all traces within its scope into a named experiment.

    Every trace started inside this block gets ``tags["traceai.experiment"] = name``.
    Tagged traces are treated as a **comparable family** in the dashboard —
    you can select any two and click Compare without them needing to be replay-linked.

    Example::

        import traceai

        with traceai.experiment("gpt-vs-claude"):
            ask_openai(prompt)
            ask_anthropic(prompt)
    """
    return tracer.experiment(name)


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
from traceai.tracer import SpanContext, Tracer, _ExperimentCM  # noqa: E402

tracer: Tracer = Tracer()
