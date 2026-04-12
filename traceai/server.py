from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import tomli_w
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from traceai.costs import get_cost_usd
from traceai.models import Span, SpanKind, SpanStatus, Trace
from traceai.storage import TraceStore

_CONFIG_PATH = Path.home() / ".traceai" / "config.toml"

# ---------------------------------------------------------------------------
# Provider registry — provider-agnostic key / model / replay management
# ---------------------------------------------------------------------------

# OpenAI-compatible providers and their base URLs (used by the openai SDK).
_OPENAI_COMPAT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "deepseek": "https://api.deepseek.com",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "perplexity": "https://api.perplexity.ai",
}

# Well-known providers — always shown in the UI even when unconfigured.
_WELL_KNOWN_PROVIDERS: list[str] = sorted(
    list(_OPENAI_COMPAT_BASE_URLS) + ["anthropic"]
)

# Curated model lists per provider (returned by GET /api/models).
_CURATED_MODELS: dict[str, list[str]] = {
    "openai": [
        "gpt-4o", "gpt-4o-mini",
        "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
        "o3", "o3-mini", "o4-mini",
    ],
    "anthropic": [
        "claude-opus-4-6", "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ],
    "mistral": [
        "mistral-large-latest", "mistral-medium-latest",
        "mistral-small-latest", "open-mistral-nemo",
    ],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "groq": [
        "llama-3.3-70b-versatile", "llama-3.1-8b-instant",
        "mixtral-8x7b-32768", "gemma2-9b-it",
    ],
    "together": [
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
    ],
    "fireworks": [
        "accounts/fireworks/models/llama-v3p3-70b-instruct",
    ],
    "openrouter": [
        "openai/gpt-4o", "anthropic/claude-sonnet-4-6",
        "google/gemini-2.5-pro",
    ],
    "perplexity": ["sonar-pro", "sonar", "sonar-reasoning-pro"],
}


# ---------------------------------------------------------------------------
# Key management helpers (provider-agnostic)
# ---------------------------------------------------------------------------


def _resolve_api_key(provider: str) -> str | None:
    """Resolve an API key from env var (``{PROVIDER}_API_KEY``) or config file.

    Priority: environment variable → ``~/.traceai/config.toml`` ``[keys]``.
    """
    env_var = f"{provider.upper()}_API_KEY"
    val = os.environ.get(env_var)
    if val:
        return val
    toml_key = f"{provider}_api_key"
    if _CONFIG_PATH.exists():
        try:
            cfg = tomllib.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            val = cfg.get("keys", {}).get(toml_key)
            if val:
                return val  # type: ignore[return-value]
        except Exception:
            pass
    return None


def _save_api_key(provider: str, key: str) -> None:
    """Persist an API key to ``~/.traceai/config.toml`` under ``[keys]``."""
    toml_key = f"{provider}_api_key"
    cfg: dict[str, Any] = {}
    if _CONFIG_PATH.exists():
        try:
            cfg = tomllib.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    keys_section = dict(cfg.get("keys", {}))
    keys_section[toml_key] = key
    cfg["keys"] = keys_section
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(tomli_w.dumps(cfg), encoding="utf-8")


def _delete_api_key(provider: str) -> None:
    """Remove an API key from ``~/.traceai/config.toml``."""
    toml_key = f"{provider}_api_key"
    if not _CONFIG_PATH.exists():
        return
    try:
        cfg = tomllib.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    keys_section = dict(cfg.get("keys", {}))
    keys_section.pop(toml_key, None)
    cfg["keys"] = keys_section
    _CONFIG_PATH.write_text(tomli_w.dumps(cfg), encoding="utf-8")


def _discover_providers() -> set[str]:
    """Discover all providers that have a configured API key (env or config)."""
    providers: set[str] = set()
    for p in _WELL_KNOWN_PROVIDERS:
        if os.environ.get(f"{p.upper()}_API_KEY"):
            providers.add(p)
    if _CONFIG_PATH.exists():
        try:
            cfg = tomllib.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            for key, val in cfg.get("keys", {}).items():
                if key.endswith("_api_key") and val:
                    providers.add(key.removesuffix("_api_key"))
        except Exception:
            pass
    return providers


_DIST_DIR = Path(__file__).parent / "dashboard" / "dist"
_LEGACY_HTML = Path(__file__).parent / "dashboard" / "index.html"

_store: TraceStore | None = None


def get_store() -> TraceStore:
    if _store is None:
        raise HTTPException(status_code=503, detail="Store not initialized")
    return _store


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class TracesResponse(BaseModel):
    traces: list[Trace]
    total: int
    limit: int
    offset: int


class TraceResponse(BaseModel):
    trace: Trace


class SpansResponse(BaseModel):
    spans: list[Span]


class ReplayRequest(BaseModel):
    messages: list[dict[str, Any]] | None = None
    model: str | None = None
    provider: str | None = None


class ReplayResponse(BaseModel):
    trace_id: str
    span_id: str


class TraceReplayRequest(BaseModel):
    model: str
    provider: str | None = None  # auto-inferred from model name when omitted


class TraceReplayResponse(BaseModel):
    trace_id: str
    spans_replayed: int
    original_cost_usd: float | None
    replay_cost_usd: float | None
    original_tokens: int
    replay_tokens: int


class SetKeyRequest(BaseModel):
    provider: str
    key: str


class KeyStatus(BaseModel):
    provider: str
    is_set: bool
    source: str  # "env", "config", or "none"


# ---------------------------------------------------------------------------
# Provider helpers for replay
# ---------------------------------------------------------------------------


def _infer_provider(model: str) -> str:
    """Infer LLM provider from model name."""
    ml = model.lower()
    if ml.startswith("claude"):
        return "anthropic"
    if ml.startswith(("gpt-", "gpt4", "o1", "o3", "o4", "chatgpt")):
        return "openai"
    if ml.startswith(("mistral", "open-mistral", "codestral", "pixtral")):
        return "mistral"
    if ml.startswith("deepseek"):
        return "deepseek"
    if ml.startswith("sonar"):
        return "perplexity"
    if "/" in ml:
        # Slash-prefixed models like "openai/gpt-4o" → likely openrouter
        prefix = ml.split("/")[0]
        if prefix in _OPENAI_COMPAT_BASE_URLS or prefix in (
            "google", "meta-llama", "mistralai",
        ):
            return "openrouter"
    return "openai"  # safe default — most providers are OpenAI-compatible


def _provider_span_name(provider: str) -> str:
    """Return a canonical span name for a provider's chat completion call."""
    if provider == "anthropic":
        return "anthropic.messages.create"
    if provider == "openai":
        return "openai.chat.completions.create"
    return f"{provider}.chat.completions.create"


async def _replay_openai_compat(
    messages: list[dict[str, Any]], model: str, provider: str,
) -> dict[str, Any]:
    """Replay via any OpenAI-compatible API (OpenAI, Mistral, DeepSeek, Groq, etc.)."""
    try:
        import openai as _openai
    except ImportError:
        raise HTTPException(
            status_code=422,
            detail="openai package not installed — run: pip install openai",
        )
    api_key = _resolve_api_key(provider)
    if not api_key:
        raise HTTPException(
            status_code=422,
            detail=f"{provider.upper()}_API_KEY is not configured. "
                   f"Add it via Settings or set the environment variable.",
        )
    base_url = _OPENAI_COMPAT_BASE_URLS.get(provider, "https://api.openai.com/v1")
    client = _openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
    try:
        resp = await client.chat.completions.create(model=model, messages=messages)  # type: ignore[arg-type]
    except _openai.AuthenticationError:
        raise HTTPException(
            status_code=422, detail=f"{provider.upper()}_API_KEY is invalid",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"{provider} call failed: {exc}",
        ) from exc
    return {
        "content": resp.choices[0].message.content,
        "finish_reason": resp.choices[0].finish_reason,
        "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
        "output_tokens": resp.usage.completion_tokens if resp.usage else 0,
        "model": resp.model,
        "system": provider,
    }


async def _replay_anthropic(messages: list[dict[str, Any]], model: str) -> dict[str, Any]:
    try:
        import anthropic as _anthropic
    except ImportError:
        raise HTTPException(
            status_code=422, detail="anthropic not installed — run: pip install anthropic",
        )
    api_key = _resolve_api_key("anthropic")
    if not api_key:
        raise HTTPException(
            status_code=422,
            detail="ANTHROPIC_API_KEY is not configured. "
                   "Add it via Settings or set the environment variable.",
        )
    system = next((m["content"] for m in messages if m.get("role") == "system"), None)
    chat_messages = [m for m in messages if m.get("role") != "system"]
    client = _anthropic.AsyncAnthropic(api_key=api_key)
    kwargs: dict[str, Any] = dict(model=model, max_tokens=4096, messages=chat_messages)
    if system:
        kwargs["system"] = system
    try:
        resp = await client.messages.create(**kwargs)
    except _anthropic.AuthenticationError:
        raise HTTPException(status_code=422, detail="ANTHROPIC_API_KEY is invalid")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Anthropic call failed: {exc}") from exc
    content = resp.content[0].text if resp.content else None
    return {
        "content": content,
        "finish_reason": resp.stop_reason,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "model": resp.model,
        "system": "anthropic",
    }


async def _dispatch_replay(
    messages: list[dict[str, Any]], model: str, provider: str,
) -> dict[str, Any]:
    """Route a replay request to the appropriate provider SDK."""
    if provider == "anthropic":
        return await _replay_anthropic(messages, model)
    return await _replay_openai_compat(messages, model, provider)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(db_path: Path | None = None) -> FastAPI:
    global _store
    _store = TraceStore(db_path=db_path)

    app = FastAPI(title="TraceAI", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount pre-built React assets when the dist/ bundle is present.
    # Falls back gracefully to vanilla index.html when running from source
    # without a frontend build (Python-only contributors, CI test jobs).
    if (_DIST_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=_DIST_DIR / "assets"), name="assets")

    _valid_statuses = {s.value for s in SpanStatus}

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        html = _DIST_DIR / "index.html"
        return FileResponse(str(html) if html.exists() else str(_LEGACY_HTML))

    # ------------------------------------------------------------------
    # Traces
    # ------------------------------------------------------------------

    @app.get("/api/traces", response_model=TracesResponse)
    async def list_traces(
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        status: Annotated[str | None, Query()] = None,
        q: Annotated[str | None, Query()] = None,
        store: TraceStore = Depends(get_store),
    ) -> TracesResponse:
        if status is not None and status not in _valid_statuses:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. Must be one of: {sorted(_valid_statuses)}",
            )
        traces = await store.alist_traces(limit=limit, offset=offset, status=status, q=q)
        total = await store.acount_traces(status=status, q=q)
        return TracesResponse(traces=traces, total=total, limit=limit, offset=offset)

    @app.get("/api/traces/{trace_id}", response_model=TraceResponse)
    async def get_trace(
        trace_id: str,
        store: TraceStore = Depends(get_store),
    ) -> TraceResponse:
        trace = await store.aget_trace(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="Trace not found")
        return TraceResponse(trace=trace)

    @app.get("/api/traces/{trace_id}/spans", response_model=SpansResponse)
    async def get_spans(
        trace_id: str,
        store: TraceStore = Depends(get_store),
    ) -> SpansResponse:
        spans = await store.aget_spans(trace_id)
        return SpansResponse(spans=spans)

    @app.delete("/api/traces")
    async def clear_all_traces(
        store: TraceStore = Depends(get_store),
    ) -> dict[str, int]:
        """Permanently delete all traces and spans."""
        deleted = await store.aclear_all()
        return {"deleted": deleted}

    # ------------------------------------------------------------------
    # Provider key detection & key management (provider-agnostic)
    # ------------------------------------------------------------------

    @app.get("/api/providers")
    async def get_providers() -> dict[str, bool]:
        """Return which providers have API keys configured."""
        all_providers = set(_WELL_KNOWN_PROVIDERS) | _discover_providers()
        return {p: _resolve_api_key(p) is not None for p in sorted(all_providers)}

    @app.get("/api/keys")
    async def get_keys() -> list[KeyStatus]:
        """Return the status of API keys (never exposes actual key values)."""
        all_providers = set(_WELL_KNOWN_PROVIDERS) | _discover_providers()
        result: list[KeyStatus] = []
        for provider in sorted(all_providers):
            env_var = f"{provider.upper()}_API_KEY"
            if os.environ.get(env_var):
                result.append(KeyStatus(provider=provider, is_set=True, source="env"))
            elif _resolve_api_key(provider):
                result.append(KeyStatus(provider=provider, is_set=True, source="config"))
            else:
                result.append(KeyStatus(provider=provider, is_set=False, source="none"))
        return result

    @app.post("/api/keys")
    async def set_key(req: SetKeyRequest) -> dict[str, str]:
        """Save an API key to ~/.traceai/config.toml (any provider accepted)."""
        if not req.key.strip():
            raise HTTPException(status_code=422, detail="Key cannot be empty")
        _save_api_key(req.provider, req.key.strip())
        return {"status": "ok", "provider": req.provider}

    @app.delete("/api/keys/{provider}")
    async def delete_key(provider: str) -> dict[str, str]:
        """Remove a saved API key from ~/.traceai/config.toml."""
        _delete_api_key(provider)
        return {"status": "ok", "provider": provider}

    @app.get("/api/models")
    async def get_models() -> dict[str, list[str]]:
        """Return curated models grouped by provider."""
        return {p: models for p, models in _CURATED_MODELS.items() if models}

    # ------------------------------------------------------------------
    # Span replay
    # ------------------------------------------------------------------

    @app.post("/api/spans/{span_id}/replay", response_model=ReplayResponse)
    async def replay_span(
        span_id: str,
        req: ReplayRequest,
        store: TraceStore = Depends(get_store),
    ) -> ReplayResponse:
        span = await store.aget_span(span_id)
        if span is None:
            raise HTTPException(status_code=404, detail="Span not found")
        if span.kind != SpanKind.LLM_CALL:
            raise HTTPException(status_code=422, detail="Only llm_call spans can be replayed")

        messages: list[dict[str, Any]] = req.messages or (span.inputs or {}).get("messages", [])
        model: str = (
            req.model
            or (span.inputs or {}).get("model")
            or (span.metadata or {}).get("gen_ai.request.model", "gpt-4")
        )
        # When the user specifies a model (possibly a different provider), infer from name.
        # Otherwise fall back to the provider recorded in the original span's metadata.
        provider: str = (
            req.provider
            or (_infer_provider(req.model) if req.model else None)
            or (span.metadata or {}).get("gen_ai.system", "openai")
        )

        result = await _dispatch_replay(messages, model, provider)

        original_model: str = (span.metadata or {}).get("gen_ai.request.model", "unknown")
        original_span_cost = (span.metadata or {}).get("gen_ai.usage.call_cost_usd")
        original_tokens = (
            (span.metadata or {}).get("gen_ai.usage.input_tokens", 0)
            + (span.metadata or {}).get("gen_ai.usage.output_tokens", 0)
        )

        replay_tokens = result["input_tokens"] + result["output_tokens"]
        cost = get_cost_usd(result["model"], result["input_tokens"], result["output_tokens"])

        # Use the parent trace name for a meaningful title
        original_trace = await store.aget_trace(span.trace_id)
        original_trace_name = original_trace.name if original_trace else span.name
        replay_name = f"↺ {original_trace_name} [{result['model']}]"

        comparison_meta: dict[str, Any] = {
            "replay_of_trace": span.trace_id,
            "original_model": original_model,
            "replay_model": result["model"],
            "original_cost_usd": original_span_cost,
            "replay_cost_usd": cost,
            "original_tokens": original_tokens,
            "replay_tokens": replay_tokens,
        }
        # Inherit the replay root — the ultimate original trace in this family
        replay_root = (
            (original_trace.tags or {}).get("replay_root", span.trace_id)
            if original_trace
            else span.trace_id
        )
        replay_trace = Trace(
            name=replay_name,
            tags={
                "replay_of_trace": span.trace_id,
                "replay_span": span_id,
                "replay_root": replay_root,
            },
            metadata=comparison_meta,
        )
        replay_span_obj = Span(
            trace_id=replay_trace.trace_id,
            name=_provider_span_name(result["system"]),
            kind=SpanKind.LLM_CALL,
            inputs={"messages": messages, "model": model},
        )
        span_meta: dict[str, Any] = {
            "gen_ai.system": result["system"],
            "gen_ai.request.model": result["model"],
            "gen_ai.usage.input_tokens": result["input_tokens"],
            "gen_ai.usage.output_tokens": result["output_tokens"],
        }
        if cost is not None:
            span_meta["gen_ai.usage.call_cost_usd"] = cost
        replay_span_obj.metadata = span_meta
        replay_span_obj.close(
            status=SpanStatus.OK,
            outputs={"content": result["content"], "finish_reason": result["finish_reason"]},
        )
        replay_trace.span_count = 1
        replay_trace.llm_call_count = 1
        replay_trace.total_tokens = replay_tokens
        replay_trace.total_cost_usd = cost
        replay_trace.close(status=SpanStatus.OK)

        await store.save_trace(replay_trace)
        await store.save_span(replay_span_obj)

        return ReplayResponse(trace_id=replay_trace.trace_id, span_id=replay_span_obj.span_id)

    # ------------------------------------------------------------------
    # Trace-level cascade replay (model arbitrage)
    # ------------------------------------------------------------------

    @app.post("/api/traces/{trace_id}/replay", response_model=TraceReplayResponse)
    async def replay_trace(
        trace_id: str,
        req: TraceReplayRequest,
        store: TraceStore = Depends(get_store),
    ) -> TraceReplayResponse:
        """Re-run all llm_call spans in a trace with a different model.

        Creates a complete new trace — full span hierarchy preserved, llm_call
        outputs replaced with replayed results.  Non-llm spans are copied
        verbatim so the new trace is self-contained and legible on its own.
        """
        trace = await store.aget_trace(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="Trace not found")
        all_spans = await store.aget_spans(trace_id)
        llm_spans = [s for s in all_spans if s.kind == SpanKind.LLM_CALL]
        if not llm_spans:
            raise HTTPException(status_code=422, detail="Trace has no llm_call spans to replay")

        provider = req.provider or _infer_provider(req.model)

        # --- 1. Replay every llm_call span (actual API calls) ---------------
        llm_results: dict[str, dict[str, Any]] = {}  # old_span_id → result
        total_replay_cost = 0.0
        total_replay_tokens = 0

        for span in llm_spans:
            messages: list[dict[str, Any]] = (span.inputs or {}).get("messages", [])
            result = await _dispatch_replay(messages, req.model, provider)
            cost = get_cost_usd(result["model"], result["input_tokens"], result["output_tokens"])
            if cost is not None:
                total_replay_cost += cost
            total_replay_tokens += result["input_tokens"] + result["output_tokens"]
            llm_results[span.span_id] = {**result, "cost": cost}

        # --- 2. Build span-id mapping (old → new) for hierarchy rewrite -----
        span_id_map: dict[str, str] = {s.span_id: uuid4().hex for s in all_spans}

        original_tokens = trace.total_tokens or 0
        original_cost = trace.total_cost_usd
        original_model = (llm_spans[0].metadata or {}).get("gen_ai.request.model", "unknown")

        comparison_meta: dict[str, Any] = {
            "replay_of_trace": trace_id,
            "original_model": original_model,
            "replay_model": req.model,
            "original_cost_usd": original_cost,
            "replay_cost_usd": total_replay_cost,
            "original_tokens": original_tokens,
            "replay_tokens": total_replay_tokens,
        }
        replay_root = (trace.tags or {}).get("replay_root", trace_id)
        replay_trace_obj = Trace(
            name=f"↺ {trace.name} [{req.model}]",
            tags={
                "replay_of_trace": trace_id,
                "replay_model": req.model,
                "replay_root": replay_root,
            },
            metadata=comparison_meta,
        )

        # --- 3. Reconstruct all spans with new IDs --------------------------
        new_spans: list[Span] = []
        for span in all_spans:
            new_id = span_id_map[span.span_id]
            new_parent = span_id_map.get(span.parent_span_id) if span.parent_span_id else None

            if span.kind == SpanKind.LLM_CALL:
                res = llm_results[span.span_id]
                s_meta: dict[str, Any] = {
                    "gen_ai.system": res["system"],
                    "gen_ai.request.model": res["model"],
                    "gen_ai.usage.input_tokens": res["input_tokens"],
                    "gen_ai.usage.output_tokens": res["output_tokens"],
                }
                if res["cost"] is not None:
                    s_meta["gen_ai.usage.call_cost_usd"] = res["cost"]
                messages = (span.inputs or {}).get("messages", [])
                new_span = Span(
                    span_id=new_id,
                    trace_id=replay_trace_obj.trace_id,
                    parent_span_id=new_parent,
                    name=_provider_span_name(res["system"]),
                    kind=SpanKind.LLM_CALL,
                    inputs={"messages": messages, "model": req.model},
                )
                new_span.metadata = s_meta
                new_span.close(
                    status=SpanStatus.OK,
                    outputs={"content": res["content"], "finish_reason": res["finish_reason"]},
                )
            else:
                # Copy structural span verbatim — preserves agent_step/tool_call context
                new_span = Span(
                    span_id=new_id,
                    trace_id=replay_trace_obj.trace_id,
                    parent_span_id=new_parent,
                    name=span.name,
                    kind=span.kind,
                    inputs=span.inputs,
                )
                new_span.metadata = span.metadata
                new_span.close(status=span.status, outputs=span.outputs)

            new_spans.append(new_span)

        replay_trace_obj.span_count = len(new_spans)
        replay_trace_obj.llm_call_count = len(llm_spans)
        replay_trace_obj.total_tokens = total_replay_tokens
        replay_trace_obj.total_cost_usd = total_replay_cost
        replay_trace_obj.close(status=SpanStatus.OK)

        await store.save_trace(replay_trace_obj)
        for s in new_spans:
            await store.save_span(s)

        return TraceReplayResponse(
            trace_id=replay_trace_obj.trace_id,
            spans_replayed=len(llm_spans),
            original_cost_usd=original_cost,
            replay_cost_usd=total_replay_cost,
            original_tokens=original_tokens,
            replay_tokens=total_replay_tokens,
        )

    return app


# ---------------------------------------------------------------------------
# Server entrypoint
# ---------------------------------------------------------------------------


def run_server(
    db_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    import uvicorn

    app = create_app(db_path=db_path)
    uvicorn.run(app, host=host, port=port)
