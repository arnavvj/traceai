# Changelog

All notable changes to TraceAI are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [0.5.0] — 2025-04-14

### Added
- **Streaming support** — `stream=True` calls on OpenAI and Anthropic are now fully captured. Content is buffered from delta events; token counts are extracted from the final chunk. `gen_ai.streaming: true` is recorded in span metadata. Async streaming (`AsyncStream`, `AsyncMessageStream`) is supported identically.
- **Head sampling** — `traceai.configure(sample_rate=0.5)` captures a random fraction of traces globally. `@tracer.trace(sample_rate=0.1)` sets a per-function rate. Sampled-out functions execute normally with zero overhead from span creation or DB writes.
- **OTel semantic conventions** — spans now carry standard GenAI attributes: `gen_ai.request.temperature`, `gen_ai.request.max_tokens`, and `gen_ai.response.finish_reason`.
- **Experiments** — `traceai.experiment("name")` context manager tags all enclosed traces with `traceai.experiment`. Tagged traces form a comparable family in the dashboard — any two can be selected for side-by-side comparison without being replay-linked.
- **`GET /api/experiments`** — aggregate stats (count, tokens, cost, date range) grouped by experiment name.
- **`GET /api/experiments/{name}/traces`** — all traces for a named experiment.
- **`py.typed` marker** — PEP 561 marker file included so type checkers recognise TraceAI's inline types.
- **Examples** — `streaming_openai.py`, `streaming_anthropic.py`, `multi_provider.py`, `sampling.py`.

### Changed
- Version `0.1.0` → `0.5.0`.
- Development status `Alpha` → `Beta`.
- `pyproject.toml`: added `artifacts` override so the pre-built dashboard bundle is included in the wheel even when gitignored.
- `traceai/__init__.py`: exports `configure`, `experiment`, `__version__`.
- `traceai/server.py`: uses `__version__` dynamically rather than a hardcoded string.
- `traceai/cli.py`: uses `__version__` dynamically.
- Dashboard `compare.ts`: `replayFamily()` checks `traceai.experiment` tag before replay lineage, so experiment traces are immediately comparable.
- Dashboard `TraceListItem.tsx`: experiment badge (⇄ name) shown in trace meta row.

---

## [0.4.0] — 2025-03-28

### Added
- **Model Replay** — any `llm_call` span can be re-run via `POST /api/spans/{id}/replay` with an optional model override. The replayed call is saved as a new linked trace and the dashboard navigates to it automatically.
- **Trace-level Cascade Replay** — `POST /api/traces/{id}/replay` re-runs all `llm_call` spans in sequence with the chosen model, creating a fully linked replay trace.
- **Model Arbitrage** — comparison banner on replayed traces shows: original model → replay model, cost savings %, token delta.
- **Compare View** — select any two traces in the same replay/experiment family and view a side-by-side diff of span outputs.
- **ModelPicker** — single smart dropdown grouping OpenAI and Anthropic models; key detection via `GET /api/providers`; custom model option.
- **ReplayBanner** — cost comparison summary shown at the top of replayed traces. Same-model replay shows a non-determinism note instead of savings %.
- **Span replay prompt playground** — editable message cards on any `llm_call` span so you can modify the prompt before replaying.
- **Replay root tag propagation** — `tags.replay_root` is set on every replay so multi-generation replay chains remain comparable.
- **`GET /api/providers`** — returns `{openai: bool, anthropic: bool}` based on environment key presence.
- **`aget_span(span_id)`** — new async method on `TraceStore` for single-span lookup.

### Changed
- Span replay now stores full comparison metadata (original model, original cost, token counts) to match trace replay format, enabling `ReplayBanner` to render on span replays.
- `SpanDetail` button renamed from "▶ Replay" → "▶ Replay Span".
- `TraceHeader` button renamed from "↺ Replay Entire Trace" → "↺ Replay All LLM Calls".
- UI spacing and typography tightened across `SpanDetail`, `TraceHeader`, and `ModelPicker`.

---

## [0.3.0] — 2025-03-10

### Added
- **React dashboard** — full rewrite of the dashboard from a single HTML file to a React 18 + TypeScript + Vite + Tailwind CSS application.
- **Trace list** with status badges, duration, token count, cost, and timestamp.
- **Span waterfall** — visual tree with indented connector lines showing parent/child relationships.
- **Span detail panel** — full inputs, outputs, metadata, and error details with JSON viewer.
- **Trace header** — summary bar with total cost, token count, duration, status, and span count.
- **Search and filter** — filter traces by name (substring) and status (ok / error / pending).
- **Pagination** — server-side pagination via `limit` and `offset` query parameters.
- **`GET /api/traces`** — paginated list with total count.
- **`GET /api/traces/{id}`** — single trace detail.
- **`GET /api/spans/{id}`** — single span detail.
- **StatusBadge** component with colour coding: green (ok), red (error), yellow (pending).
- Span kind colour coding in the waterfall.

### Changed
- Server now serves the React bundle from `traceai/dashboard/dist/` when present, falling back to the legacy `index.html`.
- `traceai open` waits for the server to be ready before opening the browser.

---

## [0.2.0] — 2025-02-24

### Added
- **OpenAI auto-instrumentation** — `traceai.instrument("openai")` patches `openai.resources.chat.completions.Completions.create` (sync and async). Captures model, messages, response content, token usage, cost, and finish reason.
- **Anthropic auto-instrumentation** — `traceai.instrument("anthropic")` patches `anthropic.resources.messages.Messages.create` (sync and async). Captures model, messages, response content, token usage, cost.
- **Cost estimation** — `traceai/costs.py` with `get_cost_usd(model, input_tokens, output_tokens)`. Bundled `fallback_prices.json` for offline pricing; graceful `None` when a model is unknown.
- **`TraceStore.aget_spans(trace_id)`** — async bulk span fetch used by the dashboard.
- **`TraceStore.aclear_all()`** — async bulk delete (used by `traceai delete --all`).
- **`traceai delete <id>`** CLI command.
- **`traceai export <id>`** CLI command (JSON output).
- **`traceai config`** subcommands: `show`, `get`, `set`.

### Changed
- `traceai.instrument()` now dispatches by provider string; previously a no-op stub.
- `traceai open` now starts a background `uvicorn` process and opens a browser tab.

---

## [0.1.0] — 2025-02-10

### Added
- **Core `Tracer`** class with `@tracer.trace` decorator and `tracer.span()` context manager.
- **`ContextVar`-based** async-safe context propagation — correctly handles `asyncio.gather()` and concurrent tasks.
- **`SpanContext`** with `set_input()`, `set_output()`, `set_metadata()`, `record_error()`.
- **`Span`**, **`Trace`**, **`SpanKind`**, **`SpanStatus`**, **`ErrorDetail`** — Pydantic v2 models.
- **`TraceStore`** — SQLite-backed storage with WAL mode at `~/.traceai/traces.db`. Sync and async read/write methods. Foreign key cascade on trace delete.
- **`traceai list`** CLI command with rich table output.
- **`traceai inspect <id>`** CLI command with span tree.
- **`traceai open`** CLI command (stub — serves legacy `index.html`).
- **66 tests** across models, storage, and tracer.
- **GitHub Actions** CI workflow (pytest, ruff, mypy on Python 3.11–3.13).
- **Release workflow** — builds wheel + sdist, publishes to PyPI on tag push.
- Example scripts: `basic_trace.py`, `custom_agent.py`, `openai_agent.py`, `anthropic_agent.py`.

---

<!-- Links -->
[0.5.0]: https://github.com/arnavvj/traceai/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/arnavvj/traceai/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/arnavvj/traceai/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/arnavvj/traceai/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/arnavvj/traceai/releases/tag/v0.1.0
