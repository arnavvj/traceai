"""
Core Tracer — Phase 2 implementation.

This module provides the Tracer class, SpanContext, and ContextVar-based
async-safe context propagation. Full implementation coming in Phase 2.
"""

from __future__ import annotations

# Placeholder — Phase 2 will implement:
#   - Tracer class with @trace decorator and span() context manager
#   - SpanContext for live span manipulation
#   - contextvars.ContextVar for async-safe trace/span propagation
#   - Auto-save to TraceStore on span/trace close
#   - Exception capture and re-raise


class SpanContext:
    """Live handle to an open span. Returned by `with tracer.span(...) as span:`"""

    # Phase 2 implementation
    pass


class Tracer:
    """
    Global tracer. Use the singleton from traceai.tracer rather than
    instantiating this directly.

    Usage:
        from traceai import tracer

        @tracer.trace
        def my_agent(prompt): ...

        with tracer.span("step", kind="llm_call") as span:
            span.set_input({"prompt": prompt})
            ...
    """

    # Phase 2 implementation
    pass
