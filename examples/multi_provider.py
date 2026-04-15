"""
Multi-provider example — run the same prompt through OpenAI and Anthropic,
then compare cost and token usage side by side.

This is the model arbitrage pattern: identical task, different providers,
instant cost comparison from a single TraceAI dashboard run.

Requires: OPENAI_API_KEY and ANTHROPIC_API_KEY set in the environment.

Run:
    python examples/multi_provider.py
    traceai open
"""

import os

import traceai

traceai.instrument("openai")
traceai.instrument("anthropic")

import anthropic  # noqa: E402
import openai  # noqa: E402

PROMPT = (
    "Explain the concept of gradient descent in machine learning in exactly two concise sentences."
)


@traceai.tracer.trace(name="openai-response")
def ask_openai(prompt: str) -> str:
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=128,
    )
    return response.choices[0].message.content or ""


@traceai.tracer.trace(name="anthropic-response")
def ask_anthropic(prompt: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=128,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text if response.content else ""


def _span_summary(store: "traceai.TraceStore", trace_id: str) -> dict:
    spans = store.get_spans(trace_id)
    llm = next((s for s in spans if s.kind.value == "llm_call"), None)
    if llm is None or llm.metadata is None:
        return {}
    m = llm.metadata
    return {
        "model": m.get("gen_ai.request.model", "?"),
        "input_tok": m.get("gen_ai.usage.input_tokens"),
        "output_tok": m.get("gen_ai.usage.output_tokens"),
        "cost_usd": m.get("gen_ai.usage.call_cost_usd"),
        "finish": m.get("gen_ai.response.finish_reason"),
    }


if __name__ == "__main__":
    from traceai import TraceStore

    store = TraceStore()

    print("=" * 60)
    print("TraceAI — Multi-Provider Comparison Example")
    print("=" * 60)
    print(f"\nPrompt: {PROMPT}\n")

    # Group both calls under one experiment so the dashboard lets you
    # select and compare them side-by-side (⇄ Compare button).
    with traceai.experiment("gradient-descent-comparison"):
        print("[1] Asking OpenAI gpt-4o-mini...")
        oai_answer = ask_openai(PROMPT)
        print(f"    {oai_answer[:120]}...\n" if len(oai_answer) > 120 else f"    {oai_answer}\n")

        print("[2] Asking Anthropic claude-haiku-4-5...")
        ant_answer = ask_anthropic(PROMPT)
        print(f"    {ant_answer[:120]}...\n" if len(ant_answer) > 120 else f"    {ant_answer}\n")

    print("=" * 60)
    print("Cost & token comparison:")
    print("-" * 60)
    traces = store.list_traces()
    for t in traces:
        info = _span_summary(store, t.trace_id)
        if not info:
            continue
        cost_str = f"${info['cost_usd']:.6f}" if info["cost_usd"] is not None else "n/a"
        print(
            f"  {t.name:<22}  model={info['model']:<26}"
            f"  in={info['input_tok']}  out={info['output_tok']}  cost={cost_str}"
        )

    print("\nRun `traceai open` to compare both traces side-by-side in the dashboard.")
