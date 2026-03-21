"""
OpenAI auto-instrumentation example — with nested span hierarchy.

Shows three agents:
  1. research_agent    — flat: one LLM call directly inside the trace
  2. multi_step_agent  — nested: each step is an AGENT_STEP span that
                         wraps its own LLM call as a child
  3. tool_agent        — nested: agent step → tool call → LLM call (3 levels)

Requires: pip install traceai[openai]
          OPENAI_API_KEY environment variable

Run:
    OPENAI_API_KEY=sk-... python examples/openai_agent.py
    traceai open
"""

import os

import openai

import traceai
from traceai import TraceStore, tracer
from traceai.models import SpanKind

# Patch once at startup — applies globally to all OpenAI client instances.
traceai.instrument("openai")

client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "sk-fake"))


# ---------------------------------------------------------------------------
# Agent 1: flat — LLM call sits directly under the trace (no parent span)
# ---------------------------------------------------------------------------


@tracer.trace(name="research-agent", tags={"style": "flat"})
def research_agent(query: str) -> str:
    """Single LLM call with no wrapping span — shows up as a root-level span."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a concise research assistant."},
            {"role": "user", "content": query},
        ],
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Agent 2: two-level nesting — AGENT_STEP → LLM_CALL
#
# Trace: "multi-step-agent"
# ├── Span: "rephrase-step"  [AGENT_STEP]
# │    └── Span: "openai.chat..."  [LLM_CALL]   ← auto-captured inside step
# └── Span: "answer-step"  [AGENT_STEP]
#      └── Span: "openai.chat..."  [LLM_CALL]   ← auto-captured inside step
# ---------------------------------------------------------------------------


@tracer.trace(name="multi-step-agent", tags={"style": "nested"})
def multi_step_agent(query: str) -> str:
    """Two agent steps, each wrapping its own LLM call."""
    # Step 1: rephrase — LLM call becomes a child of this span automatically
    with tracer.span("rephrase-step", kind=SpanKind.AGENT_STEP) as step1:
        step1.set_input({"query": query})
        rephrase = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"Rephrase more precisely: {query}"}],
        )
        rephrased = rephrase.choices[0].message.content or query
        step1.set_output({"rephrased": rephrased})

    # Step 2: answer — LLM call becomes a child of this span automatically
    with tracer.span("answer-step", kind=SpanKind.AGENT_STEP) as step2:
        step2.set_input({"rephrased_query": rephrased})
        answer = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Answer concisely."},
                {"role": "user", "content": rephrased},
            ],
        )
        result = answer.choices[0].message.content or ""
        step2.set_output({"answer": result})

    return result


# ---------------------------------------------------------------------------
# Agent 3: three-level nesting — AGENT_STEP → TOOL_CALL → LLM_CALL
#
# Trace: "tool-agent"
# └── Span: "research-step"  [AGENT_STEP]
#      └── Span: "web-search"  [TOOL_CALL]
#           └── Span: "openai.chat..."  [LLM_CALL]  ← auto-captured inside tool
# ---------------------------------------------------------------------------


@tracer.trace(name="tool-agent", tags={"style": "deep-nested"})
def tool_agent(query: str) -> str:
    """Three levels: agent step → tool call → LLM call."""
    with tracer.span("research-step", kind=SpanKind.AGENT_STEP) as step:
        step.set_input({"query": query})

        # Simulate a tool call that internally uses an LLM
        with tracer.span("web-search", kind=SpanKind.TOOL_CALL) as tool:
            tool.set_input({"search_query": query})

            # This LLM call is a child of "web-search", which is a child of "research-step"
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Simulate web search results for the query.",
                    },
                    {"role": "user", "content": query},
                ],
            )
            result = response.choices[0].message.content or ""
            tool.set_output({"results": result})

        step.set_output({"answer": result})

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    store = TraceStore()

    print("=" * 60)
    print("TraceAI — Nested Span Hierarchy Example")
    print("=" * 60)

    if not os.environ.get("OPENAI_API_KEY"):
        print("\nWARNING: OPENAI_API_KEY not set — API calls will fail.")
        print("Set it with: export OPENAI_API_KEY=sk-...\n")

    print("\n[1] Flat agent (1 LLM call, no nesting)...")
    try:
        r = research_agent("What is the speed of light?")
        print(f"    Answer: {r[:80]}")
    except Exception as e:
        print(f"    Error: {type(e).__name__}: {e}")

    print("\n[2] Multi-step agent (2 AGENT_STEP spans, each with 1 child LLM call)...")
    try:
        r = multi_step_agent("How does GPS work?")
        print(f"    Answer: {r[:80]}")
    except Exception as e:
        print(f"    Error: {type(e).__name__}: {e}")

    print("\n[3] Tool agent (AGENT_STEP → TOOL_CALL → LLM_CALL, 3 levels deep)...")
    try:
        r = tool_agent("What are black holes?")
        print(f"    Answer: {r[:80]}")
    except Exception as e:
        print(f"    Error: {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    traces = store.list_traces(limit=3)
    print(f"Latest {len(traces)} trace(s):\n")
    for t in traces:
        spans = store.get_spans(t.trace_id)
        print(f"  [{t.trace_id[:8]}] {t.name}  {t.status.value}  {t.duration_ms:.1f}ms")
        # Print span tree
        by_parent: dict[str, list] = {}
        for s in spans:
            key = s.parent_span_id or "__root__"
            by_parent.setdefault(key, []).append(s)

        def print_tree(parent_id: str, depth: int) -> None:
            for s in by_parent.get(parent_id, []):
                indent = "  " * depth
                prefix = "└── " if depth > 0 else "├── "
                print(f"    {indent}{prefix}{s.name}  [{s.kind.value}]")
                print_tree(s.span_id, depth + 1)

        print_tree("__root__", 0)
        print()

    print("Run: traceai open")
    print("     → click a trace to see the nested span tree in the UI")
