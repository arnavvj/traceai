"""
Custom agent tracing example — framework-agnostic manual spans.

Shows how to trace any Python code with full control over what gets captured.
No framework, no API keys needed.

Run:
    python examples/custom_agent.py
"""

import time

from traceai import SpanKind, tracer


class FakeMemory:
    """Simulates a vector memory store."""
    _store = {
        "paris": "Paris is the capital of France.",
        "photosynthesis": "Photosynthesis converts light to chemical energy.",
    }

    def search(self, query: str) -> list[str]:
        return [v for k, v in self._store.items() if k in query.lower()]


class FakeLLM:
    """Simulates an LLM call."""
    def complete(self, prompt: str) -> tuple[str, int, int]:
        time.sleep(0.01)
        return f"Based on context: {prompt[:40]}...", len(prompt.split()), 50


@tracer.trace(name="rag-agent", tags={"framework": "custom", "version": "1.0"})
def rag_agent(query: str) -> str:
    """
    A Retrieval-Augmented Generation agent with full tracing.

    Demonstrates:
    - SpanKind.RETRIEVAL for memory/vector search
    - SpanKind.LLM_CALL with token metadata
    - SpanKind.AGENT_STEP for orchestration logic
    - Manual error recording with span.record_error()
    """
    memory = FakeMemory()
    llm = FakeLLM()

    # Step 1: Retrieve relevant context
    with tracer.span("memory-search", kind=SpanKind.RETRIEVAL) as span:
        span.set_input({"query": query, "top_k": 3})
        results = memory.search(query)
        span.set_output({"results": results, "count": len(results)})
        span.set_metadata({"retrieval.source": "fake-vector-db"})

    # Step 2: Build prompt
    with tracer.span("build-prompt", kind=SpanKind.AGENT_STEP) as span:
        context = " ".join(results) if results else "No context found."
        prompt = f"Context: {context}\n\nQuestion: {query}\n\nAnswer:"
        span.set_input({"context_chunks": len(results), "query": query})
        span.set_output({"prompt_length": len(prompt)})

    # Step 3: LLM call
    with tracer.span("llm-generate", kind=SpanKind.LLM_CALL) as span:
        span.set_input({
            "messages": [{"role": "user", "content": prompt}],
        })
        span.set_metadata({
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.system": "openai",
        })
        response, input_tokens, output_tokens = llm.complete(prompt)
        span.set_output({"content": response})
        span.set_metadata({
            "gen_ai.usage.input_tokens": input_tokens,
            "gen_ai.usage.output_tokens": output_tokens,
        })

    return response


if __name__ == "__main__":
    from traceai import TraceStore

    store = TraceStore()

    print("=" * 60)
    print("TraceAI — Custom Agent Example")
    print("=" * 60)

    queries = [
        "What is the capital of France?",
        "Explain photosynthesis briefly.",
        "Who invented the telephone?",  # no context — tests empty retrieval
    ]

    for query in queries:
        print(f"\nQuery: {query}")
        result = rag_agent(query)
        print(f"Result: {result}")

    print("\n" + "=" * 60)
    traces = store.list_traces()
    print(f"\nRecorded {len(traces)} traces. Last 3 runs:")
    for t in traces[:3]:
        spans = store.get_spans(t.trace_id)
        print(f"\n  Trace: {t.name} [{t.trace_id[:8]}]")
        print(f"  Status: {t.status.value} | Duration: {t.duration_ms:.1f}ms | Spans: {len(spans)}")
        for s in spans:
            duration = f"{s.duration_ms:.1f}ms" if s.duration_ms else "?"
            print(f"    [{s.kind.value:14}] {s.name} ({duration})")
