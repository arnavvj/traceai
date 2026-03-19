"""
OpenAI auto-instrumentation example.

Demonstrates traceai.instrument("openai") — no manual span code needed.
Every client.chat.completions.create() call is automatically traced.

Requires: pip install traceai[openai]
          OPENAI_API_KEY environment variable

Run:
    OPENAI_API_KEY=sk-... python examples/openai_agent.py
    traceai list
    traceai inspect <trace_id>
"""

import os

import openai

import traceai
from traceai import TraceStore, tracer

# Patch once at startup — applies globally to all OpenAI client instances.
traceai.instrument("openai")

client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "sk-fake"))


@tracer.trace(name="research-agent", tags={"provider": "openai"})
def research_agent(query: str) -> str:
    """
    Single-call agent. The llm_call span is created automatically —
    no 'with tracer.span(...)' needed.
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a concise research assistant."},
            {"role": "user", "content": query},
        ],
    )
    return response.choices[0].message.content or ""


@tracer.trace(name="multi-step-agent")
def multi_step_agent(query: str) -> str:
    """Two LLM calls in one trace — each becomes its own child span."""
    # Step 1: rephrase
    rephrase = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Rephrase more precisely: {query}"}],
    )
    rephrased = rephrase.choices[0].message.content or query

    # Step 2: answer
    answer = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Answer concisely."},
            {"role": "user", "content": rephrased},
        ],
    )
    return answer.choices[0].message.content or ""


if __name__ == "__main__":
    store = TraceStore()

    print("=" * 60)
    print("TraceAI — OpenAI Auto-Instrumentation Example")
    print("=" * 60)

    if not os.environ.get("OPENAI_API_KEY"):
        print("\nWARNING: OPENAI_API_KEY not set — API calls will fail.")
        print("Set it with: export OPENAI_API_KEY=sk-...\n")

    print("\n[1] Running research agent...")
    try:
        result = research_agent("What is the speed of light?")
        print(f"    Answer: {result[:80]}")
    except Exception as e:
        print(f"    Error (expected without real API key): {type(e).__name__}: {e}")

    print("\n[2] Running multi-step agent...")
    try:
        result2 = multi_step_agent("How does GPS work?")
        print(f"    Answer: {result2[:80]}")
    except Exception as e:
        print(f"    Error (expected without real API key): {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    traces = store.list_traces()
    print(f"Recorded {len(traces)} trace(s):")
    for t in traces:
        spans = store.get_spans(t.trace_id)
        llm_spans = [s for s in spans if s.kind.value == "llm_call"]
        print(f"\n  [{t.trace_id[:8]}] {t.name}  {t.status.value}  {t.duration_ms:.1f}ms")
        print(f"  LLM calls auto-captured: {len(llm_spans)}")
        for s in llm_spans:
            meta = s.metadata or {}
            tokens_in = meta.get("gen_ai.usage.input_tokens", "?")
            tokens_out = meta.get("gen_ai.usage.output_tokens", "?")
            print(f"    {s.name}  tokens: {tokens_in} in / {tokens_out} out")

    print("\nRun: traceai list")
    if traces:
        print(f"Run: traceai inspect {traces[0].trace_id[:8]}")
