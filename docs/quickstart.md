# QuickStart Guide

This guide takes you from zero to a fully instrumented AI agent in under five minutes.

---

## Table of Contents

1. [Installation](#1-installation)
2. [Your First Trace](#2-your-first-trace)
3. [Auto-Instrument OpenAI](#3-auto-instrument-openai)
4. [Auto-Instrument Anthropic](#4-auto-instrument-anthropic)
5. [Streaming Calls](#5-streaming-calls)
6. [Manual Instrumentation](#6-manual-instrumentation)
7. [The Dashboard](#7-the-dashboard)
8. [The CLI](#8-the-cli)
9. [Sampling](#9-sampling)
10. [Experiments & Model Comparison](#10-experiments--model-comparison)
11. [Replay & Model Arbitrage](#11-replay--model-arbitrage)
12. [Key Management](#12-key-management)
13. [Configuration Reference](#13-configuration-reference)

---

## 1. Installation

```bash
pip install traceai
```

For auto-instrumentation with specific providers:

```bash
pip install "traceai[openai]"       # includes openai>=1.0
pip install "traceai[anthropic]"    # includes anthropic>=0.25
pip install "traceai[openai,anthropic]"   # both
```

Requires Python 3.11+. No cloud account. No Docker. No signup.

All trace data is stored locally at `~/.traceai/traces.db` (SQLite).

---

## 2. Your First Trace

No LLM key required — this example uses plain Python:

```python
import traceai

@traceai.tracer.trace
def analyse_text(text: str) -> dict:
    with traceai.tracer.span("tokenise", kind="custom") as span:
        span.set_input({"text": text})
        tokens = text.split()
        span.set_output({"token_count": len(tokens)})

    with traceai.tracer.span("classify", kind="agent_step") as span:
        span.set_input({"tokens": tokens})
        label = "long" if len(tokens) > 10 else "short"
        span.set_output({"label": label})

    return {"tokens": len(tokens), "label": label}

result = analyse_text("The quick brown fox jumps over the lazy dog")
print(result)
```

```bash
traceai list          # see the trace in the terminal
traceai open          # open the dashboard in your browser
```

Every call to `analyse_text` produces one **trace** containing two **spans**. You can inspect inputs, outputs, duration, and status for each span.

---

## 3. Auto-Instrument OpenAI

Call `traceai.instrument("openai")` once — before any OpenAI client is created — and every `chat.completions.create` call is captured automatically:

```python
import traceai
traceai.instrument("openai")   # must come before importing openai

from openai import OpenAI

client = OpenAI()   # reads OPENAI_API_KEY from environment

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a concise assistant."},
        {"role": "user",   "content": "What is gradient descent?"},
    ],
    temperature=0.3,
    max_tokens=128,
)
print(response.choices[0].message.content)
```

TraceAI captures without any further changes:

| Field | Where it appears |
|---|---|
| Model name | `gen_ai.request.model` in span metadata |
| Full messages | `span.inputs.messages` |
| Full response | `span.outputs.content` |
| Input / output tokens | `gen_ai.usage.input_tokens` / `output_tokens` |
| Estimated cost | `gen_ai.usage.call_cost_usd` |
| Temperature & max_tokens | `gen_ai.request.temperature` / `max_tokens` |
| Finish reason | `gen_ai.response.finish_reason` |
| Duration | `span.duration_ms` |

### Async OpenAI

```python
import asyncio, traceai
traceai.instrument("openai")

from openai import AsyncOpenAI

async def main():
    client = AsyncOpenAI()
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Explain async/await in Python."}],
    )
    print(response.choices[0].message.content)

asyncio.run(main())
```

Works identically — async calls produce the same span structure.

---

## 4. Auto-Instrument Anthropic

```python
import traceai
traceai.instrument("anthropic")   # before importing anthropic

import anthropic

client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from environment

message = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=256,
    system="You are a concise assistant.",
    messages=[{"role": "user", "content": "What is gradient descent?"}],
    temperature=0.3,
)
print(message.content[0].text)
```

### Async Anthropic

```python
import asyncio, traceai
traceai.instrument("anthropic")

import anthropic

async def main():
    client = anthropic.AsyncAnthropic()
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": "Explain async/await in Python."}],
    )
    print(message.content[0].text)

asyncio.run(main())
```

---

## 5. Streaming Calls

Pass `stream=True` as normal — TraceAI captures streaming calls transparently. Content is accumulated across chunks and token counts are extracted from the final chunk.

### OpenAI streaming

```python
import traceai
traceai.instrument("openai")

from openai import OpenAI

client = OpenAI()

# Add stream_options to get token usage on OpenAI streams
stream = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Count from 1 to 5."}],
    stream=True,
    stream_options={"include_usage": True},
)

for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()
```

The captured span will have `gen_ai.streaming: true` in its metadata plus the fully assembled `content` in outputs.

### Anthropic streaming

```python
import traceai
traceai.instrument("anthropic")

import anthropic

client = anthropic.Anthropic()

stream = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=128,
    messages=[{"role": "user", "content": "Count from 1 to 5."}],
    stream=True,
)

for event in stream:
    if getattr(event, "type", None) == "content_block_delta":
        text = getattr(event.delta, "text", None)
        if text:
            print(text, end="", flush=True)
print()
```

### Async streaming

Both providers support async streaming with `AsyncOpenAI` / `AsyncAnthropic` and `async for` — captured identically.

---

## 6. Manual Instrumentation

Use `@tracer.trace` and `tracer.span()` to instrument any Python code, regardless of which LLM or framework you use.

### Decorator

```python
from traceai import tracer

@tracer.trace                          # trace name defaults to function name
def run_agent(question: str) -> str:
    ...

@tracer.trace(name="custom-name")      # explicit name
def run_agent_v2(question: str) -> str:
    ...
```

### Context manager spans

```python
from traceai import tracer

@tracer.trace
def rag_pipeline(question: str) -> str:

    # Step 1 — retrieve context
    with tracer.span("vector-search", kind="retrieval") as span:
        span.set_input({"query": question, "top_k": 5})
        docs = vector_store.search(question, top_k=5)
        span.set_output({"doc_count": len(docs), "doc_ids": [d.id for d in docs]})

    # Step 2 — call the LLM
    with tracer.span("synthesis", kind="llm_call") as span:
        prompt = build_prompt(question, docs)
        span.set_input({"messages": [{"role": "user", "content": prompt}]})
        span.set_metadata({
            "gen_ai.system": "openai",
            "gen_ai.request.model": "gpt-4o",
        })
        answer = call_llm(prompt)
        span.set_output({"content": answer})

    return answer
```

### Recording errors

```python
with tracer.span("risky-step") as span:
    try:
        result = do_something_risky()
        span.set_output({"result": result})
    except Exception as e:
        span.record_error(e)   # marks span as error, captures type + message
        raise
```

### Async agents

```python
import asyncio
from traceai import tracer

@tracer.trace
async def async_agent(prompt: str) -> str:
    async with tracer.span("async-llm") as span:   # use async with for async spans
        span.set_input({"prompt": prompt})
        result = await call_llm_async(prompt)
        span.set_output({"content": result})
    return result
```

### Concurrent tasks

`ContextVar`-based propagation means concurrent tasks each get their own span context — no cross-contamination even with `asyncio.gather`:

```python
@tracer.trace
async def parallel_agent(questions: list[str]) -> list[str]:
    # Each gather task is independently traced under this parent trace
    results = await asyncio.gather(*[call_llm_async(q) for q in questions])
    return list(results)
```

---

## 7. The Dashboard

```bash
traceai open                          # http://localhost:7474
traceai open --port 8080              # custom port
traceai open --no-browser             # start server only (no browser tab)
traceai open --db /path/to/traces.db  # custom database location
```

### What you can do in the dashboard

**Trace list (left panel)**
- Browse all recorded traces ordered by most recent
- See name, status badge, duration, token count, estimated cost, and timestamp at a glance
- Filter by name (substring search) and status (`ok` / `error` / `pending`)
- Paginate through large trace sets
- Replay-child traces are nested under their parent with a tree connector

**Span waterfall (middle panel)**
- Expand any trace to see the full parent/child span tree
- Each span shows kind icon, name, duration, and status
- Click any span to open its detail panel
- Span kinds are colour-coded: LLM calls in indigo, tool calls in green, retrieval in amber, etc.

**Span detail (right panel)**
- Full `inputs` and `outputs` rendered as collapsible JSON
- All metadata fields (model, tokens, cost, finish reason, streaming flag, etc.)
- Error details with type, message, and traceback when a span failed
- Replay button to re-run this exact call with a different model
- Edit prompt button to open the playground (modify messages before re-running)

**Compare view**
- Select two traces from the same experiment or replay family
- Side-by-side diff showing which spans changed, which outputs differ
- Status: `identical` | `modified` | `a-only` | `b-only` per span pair

**Experiments tab**
- Aggregate stats per experiment: run count, total tokens, total cost, date range
- Click any experiment to filter the trace list to those runs

---

## 8. The CLI

The CLI lets you inspect traces without opening a browser — useful in SSH sessions, CI pipelines, or quick terminal checks.

### List traces

```bash
traceai list
```

```
 ID         Name                    Status   Duration   Tokens   Cost      Started
 a1b2c3d4   openai-response         ok       312ms      847      $0.0009   Apr 14, 10:23:01
 e5f6a7b8   anthropic-response      ok       198ms      712      $0.0003   Apr 14, 10:23:02
```

Options:
```bash
traceai list --limit 20            # show 20 traces (default: 10)
traceai list --status error        # filter by status
traceai list --db ~/myproject.db   # custom database path
```

### Inspect a trace

```bash
traceai inspect a1b2c3d4
```

```
Trace: openai-response  [a1b2c3d4]
Status: ok  •  Duration: 312ms  •  Spans: 2  •  Tokens: 847  •  Cost: $0.0009

Span tree
└── 🤖 llm_call  openai-response          312ms   ok
    inputs:
      model: gpt-4o-mini
      messages: [{"role": "user", "content": "What is gradient descent?"}]
    outputs:
      content: "Gradient descent is an optimisation algorithm..."
    metadata:
      gen_ai.request.model: gpt-4o-mini
      gen_ai.usage.input_tokens: 612
      gen_ai.usage.output_tokens: 235
      gen_ai.usage.call_cost_usd: 0.000089
      gen_ai.response.finish_reason: stop
```

### Export as JSON

```bash
traceai export a1b2c3d4             # prints JSON to stdout
traceai export a1b2c3d4 > trace.json
```

### Delete a trace

```bash
traceai delete a1b2c3d4
```

### Config management

```bash
traceai config show                     # print current config
traceai config set default_db ~/mydb.db # set a key
traceai config get default_db           # read a key
```

Config is stored at `~/.traceai/config.toml`.

---

## 9. Sampling

In high-traffic production systems, recording every trace is expensive. TraceAI supports **head sampling** — the decision to record or skip is made once at trace start, so all child spans inside a skipped trace are silent no-ops with zero overhead.

### Global sample rate

```python
import traceai

traceai.configure(sample_rate=0.1)   # capture roughly 10% of all traces
```

Call `configure()` once at application startup. The rate applies to all `@tracer.trace` calls globally.

```python
# Reset to full capture
traceai.configure(sample_rate=1.0)

# Disable tracing entirely (e.g. in tests)
traceai.configure(sample_rate=0.0)
```

### Per-function sample rate

Override the global rate on a specific decorator:

```python
# This high-volume function is traced only 5% of the time
@traceai.tracer.trace(name="bulk-processor", sample_rate=0.05)
def process_document(doc: str) -> str:
    ...

# This critical path is always traced (overrides any global rate)
@traceai.tracer.trace(name="payment-agent", sample_rate=1.0)
def handle_payment(amount: float) -> dict:
    ...
```

The per-function rate takes priority over the global rate when specified.

### Behaviour when sampled out

The decorated function still **executes normally** and returns its value. TraceAI simply does not create any spans or write anything to the database:

```python
traceai.configure(sample_rate=0.0)

result = my_agent("hello")   # runs fine, returns value, zero DB writes
```

---

## 10. Experiments & Model Comparison

An **experiment** is a named group of traces that can be compared side-by-side in the dashboard. Use `traceai.experiment()` to tag all traces in a block with a shared name.

### Basic experiment

```python
import traceai

traceai.instrument("openai")

with traceai.experiment("summarisation-v2"):
    # Run A — baseline prompt
    run_summariser(text, prompt_version="v1")

    # Run B — improved prompt
    run_summariser(text, prompt_version="v2")
```

Both traces appear in the dashboard with the `⇄ summarisation-v2` badge. Select both and click **Compare** to see a side-by-side diff.

### Cross-provider comparison

```python
import traceai

traceai.instrument("openai")
traceai.instrument("anthropic")

PROMPT = "Summarise the Python GIL in one sentence."

with traceai.experiment("gil-summary"):
    ask_openai(PROMPT)       # → trace A: gpt-4o-mini
    ask_anthropic(PROMPT)    # → trace B: claude-haiku

# Dashboard shows cost breakdown:
# gpt-4o-mini: $0.000089 · 235 tok
# claude-haiku: $0.000031 · 198 tok
# → Haiku is 65% cheaper on this task
```

### Async experiments

The `experiment()` context manager is fully async-safe:

```python
import asyncio, traceai

async def main():
    async with traceai.experiment("async-comparison"):
        await asyncio.gather(
            ask_openai_async(PROMPT),
            ask_anthropic_async(PROMPT),
        )

asyncio.run(main())
```

---

## 11. Replay & Model Arbitrage

TraceAI can re-run any recorded LLM call with a different model and save the result as a new linked trace. This is the **model arbitrage** workflow: run once, compare across models without re-writing any code.

### Replay from the dashboard

1. Open `traceai open`
2. Select any trace that contains `llm_call` spans
3. In the **Span detail** panel, click **▶ Replay Span** to re-run a single call
4. Or use the **↺ Replay All LLM Calls** button in the trace header to re-run every LLM call in the trace
5. Pick a target model from the dropdown
6. Click replay — the new trace is created and selected automatically

The comparison banner shows:
```
↺ Replayed  gpt-4o → claude-haiku-4-5-20251001
Original: $0.042 · 1,200 tok    Replay: $0.003 · 1,100 tok
Cost savings: 93%  ↓   Token delta: −8%
```

### Prompt playground

Click **✎ Edit Prompt** on any `llm_call` span to enter playground mode. Message cards become editable — modify the system prompt, user message, or any turn in the conversation, then click **▶ Run** to replay with the modified messages.

The replayed trace is linked to the original and can be compared in the Compare view.

---

## 12. Key Management

TraceAI reads provider API keys from **environment variables** — the standard approach that works with any secret manager, `.env` loader, or CI system.

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
```

Or via `.env` file with `python-dotenv`:

```python
from dotenv import load_dotenv
load_dotenv()

import traceai
traceai.instrument("openai")
# OPENAI_API_KEY is now set from .env
```

Keys are **never** read or stored by TraceAI itself — they are passed directly to the provider SDK. The dashboard's `GET /api/providers` endpoint only returns a boolean (key present/absent) to inform the model picker UI; the key value is never transmitted.

---

## 13. Configuration Reference

### `traceai.configure()`

```python
traceai.configure(
    sample_rate=1.0,   # float 0.0–1.0; fraction of traces to capture
)
```

Raises `ValueError` if `sample_rate` is outside `[0.0, 1.0]`.

### `traceai.instrument(provider)`

```python
traceai.instrument("openai")      # patches openai.resources.chat.completions
traceai.instrument("anthropic")   # patches anthropic.resources.messages
```

Must be called **before** any client is created. Safe to call multiple times (idempotent).

### `traceai.experiment(name)`

```python
# Sync
with traceai.experiment("my-experiment"):
    run_agent()

# Async
async with traceai.experiment("my-experiment"):
    await run_agent_async()
```

All traces started within the block receive `tags["traceai.experiment"] = name`. Explicit per-trace tags take priority if already set.

### `@tracer.trace` options

```python
@traceai.tracer.trace                           # defaults: name=fn.__name__, sample_rate=global
@traceai.tracer.trace(name="my-trace")          # explicit name
@traceai.tracer.trace(sample_rate=0.1)          # per-function sampling
@traceai.tracer.trace(name="t", sample_rate=0)  # always skip this function
```

Also works as a plain decorator without parentheses: `@tracer.trace`.

### `tracer.span()` options

```python
with tracer.span("name") as span:              # kind defaults to "custom"
    ...

with tracer.span("llm-call", kind="llm_call") as span:
    ...

# Async
async with tracer.span("async-step") as span:
    ...
```

Available `kind` values: `llm_call`, `tool_call`, `agent_step`, `retrieval`, `memory_read`, `memory_write`, `embedding`, `custom`.

### Database path

By default, traces are stored at `~/.traceai/traces.db`. Override per-command:

```bash
traceai list --db /path/to/other.db
traceai open --db /path/to/other.db
```

Or set a permanent default:

```bash
traceai config set default_db /path/to/other.db
```

Or programmatically:

```python
from traceai import TraceStore, Tracer

store = TraceStore(db_path="/path/to/other.db")
tracer = Tracer(store=store)
```

---

## Next Steps

- Browse [examples/](../examples/) for runnable scripts covering all major features
- Read the full [README](../README.md) for the feature overview and comparison table
- Check [CHANGELOG.md](../CHANGELOG.md) for what changed in each version
- Open an [issue](https://github.com/arnavvj/traceai/issues) if something is missing or broken
