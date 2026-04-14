"""
Streaming Anthropic example — auto-instrumentation with stream=True.

Demonstrates that TraceAI captures Anthropic streaming calls transparently:
content is accumulated from content_block_delta events, token usage is
captured from message_start / message_delta events, and stop_reason is
recorded in metadata as gen_ai.response.finish_reason.

Requires: ANTHROPIC_API_KEY set in the environment.

Run:
    python examples/streaming_anthropic.py
    traceai list
    traceai inspect <trace_id>
"""

import os

import traceai

traceai.instrument("anthropic")

import anthropic  # noqa: E402 (must come after instrument())


@traceai.tracer.trace(name="streaming-anthropic-demo")
def run_streaming_message(prompt: str) -> str:
    """Stream an Anthropic message and return the full assembled response."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Use create(stream=True) — TraceAI patches Messages.create, not the
    # high-level messages.stream() helper.
    full_content = []
    stream = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        temperature=0.7,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    for event in stream:
        if getattr(event, "type", None) == "content_block_delta":
            delta = getattr(event, "delta", None)
            text = getattr(delta, "text", None) if delta else None
            if text:
                full_content.append(text)

    return "".join(full_content)


if __name__ == "__main__":
    from traceai import TraceStore

    store = TraceStore()

    print("=" * 60)
    print("TraceAI — Streaming Anthropic Example")
    print("=" * 60)

    prompt = "List three interesting facts about neutron stars in one sentence each."
    print(f"\nPrompt: {prompt}\n")
    print("Streaming response:")
    print("-" * 40)

    response = run_streaming_message(prompt)
    print(response)

    print("\n" + "=" * 60)
    traces = store.list_traces()
    if traces:
        t = traces[0]
        spans = store.get_spans(t.trace_id)
        llm_span = next((s for s in spans if s.kind.value == "llm_call"), None)
        print(f"Trace recorded: {t.name}  [{t.trace_id[:8]}...]")
        if llm_span and llm_span.metadata:
            m = llm_span.metadata
            print(f"  model:        {m.get('gen_ai.request.model')}")
            print(f"  temperature:  {m.get('gen_ai.request.temperature')}")
            print(f"  max_tokens:   {m.get('gen_ai.request.max_tokens')}")
            print(f"  input tokens: {m.get('gen_ai.usage.input_tokens')}")
            print(f"  output tokens:{m.get('gen_ai.usage.output_tokens')}")
            print(f"  finish_reason:{m.get('gen_ai.response.finish_reason')}")
            print(f"  streaming:    {m.get('gen_ai.streaming')}")
            cost = m.get("gen_ai.usage.call_cost_usd")
            if cost is not None:
                print(f"  cost:         ${cost:.6f}")

    print("\nRun `traceai list` and `traceai open` to explore in the dashboard.")
