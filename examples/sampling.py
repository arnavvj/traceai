"""
Sampling example — configure TraceAI to capture only a fraction of traces.

Useful in high-throughput production systems where recording every trace
would be too expensive. TraceAI's head sampling makes the decision once per
trace: all child spans inside a sampled-out trace are silent no-ops, so
there is zero overhead from span creation or DB writes.

No API key required — this example uses fake LLM calls.

Run:
    python examples/sampling.py
    traceai list   # should show roughly half the expected traces
"""

import random

import traceai
from traceai import TraceStore

# ------------------------------------------------------------------
# Fake LLM call — no real API key needed for this demo
# ------------------------------------------------------------------


@traceai.tracer.trace(name="fake-agent")
def fake_agent(request_id: int) -> str:
    """Simulates an agent with an LLM call span inside."""
    with traceai.tracer.span("llm-call", kind="llm_call") as span:
        span.set_input({"request_id": request_id, "model": "gpt-4o-mini"})
        span.set_metadata(
            {
                "gen_ai.system": "openai",
                "gen_ai.request.model": "gpt-4o-mini",
                "gen_ai.usage.input_tokens": random.randint(50, 200),
                "gen_ai.usage.output_tokens": random.randint(20, 100),
            }
        )
        result = f"response-{request_id}"
        span.set_output({"content": result})
    return result


# ------------------------------------------------------------------
# Demo 1 — global sample_rate via configure()
# ------------------------------------------------------------------


def demo_global_sample_rate(store: TraceStore, rate: float, n: int = 20) -> None:
    print(f"\n[Demo 1] Global sample_rate={rate} — running {n} agents")
    traceai.configure(sample_rate=rate)

    before = len(store.list_traces())
    for i in range(n):
        fake_agent(i)
    after = len(store.list_traces())

    captured = after - before
    expected = round(n * rate)
    print(f"  Captured {captured}/{n} traces  (expected ~{expected} at {rate * 100:.0f}%)")

    # Restore full tracing for subsequent demos
    traceai.configure(sample_rate=1.0)


# ------------------------------------------------------------------
# Demo 2 — per-trace sample_rate on the decorator
# ------------------------------------------------------------------


@traceai.tracer.trace(name="rare-debug-agent", sample_rate=0.1)
def rare_debug_agent(request_id: int) -> str:
    """This agent is traced only ~10% of the time — a low-priority debug path."""
    with traceai.tracer.span("debug-step") as span:
        span.set_input({"id": request_id})
        span.set_output({"ok": True})
    return f"debug-{request_id}"


def demo_per_trace_rate(store: TraceStore, n: int = 30) -> None:
    print(f"\n[Demo 2] Per-trace sample_rate=0.1 — running {n} rare-debug-agent calls")

    before = len(store.list_traces())
    for i in range(n):
        rare_debug_agent(i)
    after = len(store.list_traces())

    captured = after - before
    expected = round(n * 0.1)
    print(f"  Captured {captured}/{n} traces  (expected ~{expected} at 10%)")


# ------------------------------------------------------------------
# Demo 3 — zero sample_rate, function still returns correctly
# ------------------------------------------------------------------


def demo_zero_rate_correctness(store: TraceStore) -> None:
    print("\n[Demo 3] sample_rate=0.0 — function must still return correct values")
    traceai.configure(sample_rate=0.0)

    before = len(store.list_traces())
    results = [fake_agent(i) for i in range(5)]
    n_new = len(store.list_traces()) - before

    print(f"  Results: {results}")
    print(f"  New traces saved: {n_new}  (expected 0 — all sampled out)")
    assert all(r.startswith("response-") for r in results), "Function return values corrupted!"
    print("  Return values are correct even when sampled out.")

    traceai.configure(sample_rate=1.0)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    # Use a fresh isolated DB for this demo so list_traces() counts are clean
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "sampling_demo.db"
        store = TraceStore(db_path=db)
        # Point the global tracer at our demo store
        traceai.tracer._store = store  # type: ignore[attr-defined]

        print("=" * 60)
        print("TraceAI — Sampling Example")
        print("=" * 60)
        print("Note: exact counts vary due to randomness — ranges are approximate.")

        demo_global_sample_rate(store, rate=0.5, n=20)
        demo_per_trace_rate(store, n=30)
        demo_zero_rate_correctness(store)

        print("\n" + "=" * 60)
        total = len(store.list_traces())
        print(f"Total traces recorded across all demos: {total}")
        print("\nKey takeaways:")
        print("  • traceai.configure(sample_rate=0.5) captures ~50% of traces globally")
        print("  • @tracer.trace(sample_rate=0.1) captures ~10% per decorated function")
        print("  • Sampled-out functions still execute and return correct values")
        print("  • All child spans inside a sampled-out trace are silent no-ops")
