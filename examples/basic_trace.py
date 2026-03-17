"""
Basic TraceAI example — no LLM API key required.

Demonstrates:
- @tracer.trace decorator (sync and async)
- with tracer.span() context manager
- Manual span input/output/metadata
- Nested spans

Run:
    python examples/basic_trace.py
    traceai list
    traceai inspect <trace_id>
"""

import asyncio
import time

from traceai import tracer

# ------------------------------------------------------------------
# Sync example
# ------------------------------------------------------------------


@tracer.trace
def research_agent(query: str) -> str:
    """A fake synchronous agent that demonstrates tracing."""

    with tracer.span("preprocess", kind="agent_step") as span:
        span.set_input({"query": query})
        processed = query.strip().lower()
        span.set_output({"processed": processed})

    with tracer.span("llm-call", kind="llm_call") as span:
        span.set_input({"messages": [{"role": "user", "content": processed}]})
        span.set_metadata(
            {
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.usage.input_tokens": 42,
                "gen_ai.usage.output_tokens": 128,
            }
        )
        # Simulate LLM latency
        time.sleep(0.05)
        response = f"The answer to '{processed}' is 42."
        span.set_output({"content": response})

    with tracer.span("postprocess", kind="agent_step") as span:
        span.set_input({"raw": response})
        result = response.upper()
        span.set_output({"result": result})

    return result


# ------------------------------------------------------------------
# Async example with nested spans
# ------------------------------------------------------------------


@tracer.trace
async def async_research_agent(query: str) -> str:
    """A fake async agent demonstrating nested span tracing."""

    async with tracer.span("plan", kind="agent_step") as span:
        span.set_input({"query": query})
        plan = ["search", "synthesize", "format"]
        span.set_output({"steps": plan})

    async with tracer.span("search", kind="tool_call") as span:
        span.set_input({"query": query})
        await asyncio.sleep(0.02)  # simulate I/O

        # Nested LLM call inside the tool
        async with tracer.span("rerank-llm", kind="llm_call") as llm_span:
            llm_span.set_input({"results": ["result_a", "result_b"]})
            llm_span.set_metadata({"gen_ai.request.model": "gpt-4o-mini"})
            await asyncio.sleep(0.02)
            llm_span.set_output({"ranked": ["result_a"]})

        span.set_output({"results": ["result_a"]})

    async with tracer.span("synthesize", kind="llm_call") as span:
        span.set_input({"context": "result_a", "query": query})
        span.set_metadata(
            {
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.usage.input_tokens": 512,
                "gen_ai.usage.output_tokens": 256,
            }
        )
        await asyncio.sleep(0.03)
        answer = f"Synthesized answer for: {query}"
        span.set_output({"content": answer})

    return answer


# ------------------------------------------------------------------
# Error example
# ------------------------------------------------------------------


@tracer.trace
def failing_agent(query: str) -> str:
    """Demonstrates how TraceAI captures errors."""
    with tracer.span("dangerous-step", kind="tool_call") as span:
        span.set_input({"query": query})
        raise ValueError(f"Tool failed: could not process '{query}'")


if __name__ == "__main__":
    from traceai import TraceStore

    store = TraceStore()

    print("=" * 60)
    print("TraceAI — Basic Trace Example")
    print("=" * 60)

    # Run sync agent
    print("\n[1] Running sync research agent...")
    result = research_agent("What is the capital of France?")
    print(f"    Result: {result[:60]}...")

    # Run async agent
    print("\n[2] Running async research agent...")
    result2 = asyncio.run(async_research_agent("How does photosynthesis work?"))
    print(f"    Result: {result2}")

    # Run failing agent
    print("\n[3] Running failing agent (expected error)...")
    try:
        failing_agent("broken query")
    except ValueError as e:
        print(f"    Caught expected error: {e}")

    # Show what was recorded
    print("\n" + "=" * 60)
    traces = store.list_traces()
    print(f"Recorded {len(traces)} traces:")
    for t in traces:
        spans = store.get_spans(t.trace_id)
        status_icon = "ok" if t.status.value == "ok" else "!!"
        print(
            f"  [{status_icon}] [{t.status.value:7}] {t.name}"
            f" - {len(spans)} span(s), {t.duration_ms:.1f}ms"
        )
        for s in spans:
            indent = "      "
            parent_marker = "+-" if s.parent_span_id else "  "
            print(f"  {indent}{parent_marker} {s.kind.value:14} {s.name}")

    print(f"\nTrace IDs saved to: {store.db_path}")
    print("\nRun these commands to explore:")
    print("  traceai list")
    if traces:
        print(f"  traceai inspect {traces[0].trace_id[:8]}...")
