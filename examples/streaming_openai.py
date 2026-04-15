"""
Streaming OpenAI example — auto-instrumentation with stream=True.

Demonstrates that TraceAI captures streaming calls transparently:
content is accumulated across chunks, token usage is captured from
the final chunk, and finish_reason is recorded in metadata.

Requires: OPENAI_API_KEY set in the environment.

Run:
    python examples/streaming_openai.py
    traceai list
    traceai inspect <trace_id>
"""

import os

import traceai

traceai.instrument("openai")

import openai  # noqa: E402 (must come after instrument())


@traceai.tracer.trace(name="streaming-openai-demo")
def run_streaming_chat(prompt: str) -> str:
    """Stream a chat completion and return the full assembled response."""
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    full_content = []
    with client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=256,
        stream=True,
        stream_options={"include_usage": True},  # needed for token counts in stream
    ) as stream:
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                full_content.append(chunk.choices[0].delta.content)

    return "".join(full_content)


if __name__ == "__main__":
    from traceai import TraceStore

    store = TraceStore()

    print("=" * 60)
    print("TraceAI — Streaming OpenAI Example")
    print("=" * 60)

    prompt = "List three interesting facts about black holes in one sentence each."
    print(f"\nPrompt: {prompt}\n")
    print("Streaming response:")
    print("-" * 40)

    response = run_streaming_chat(prompt)
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
