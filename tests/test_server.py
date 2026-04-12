"""Tests for traceai.server — FastAPI endpoints."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from traceai.models import ErrorDetail, Span, SpanKind, SpanStatus, Trace
from traceai.storage import TraceStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> TraceStore:
    return TraceStore(db_path=tmp_path / "test.db")


@pytest.fixture
def app_instance(store: TraceStore):  # type: ignore[no-untyped-def]
    from traceai.server import create_app

    return create_app(db_path=store.db_path)


@pytest_asyncio.fixture
async def client(app_instance) -> AsyncGenerator[AsyncClient, None]:  # type: ignore[no-untyped-def]
    async with AsyncClient(transport=ASGITransport(app=app_instance), base_url="http://test") as c:
        yield c


@pytest.fixture
def sample_trace() -> Trace:
    return Trace(
        name="test-agent",
        status=SpanStatus.OK,
        span_count=2,
        llm_call_count=1,
        tags={"env": "test"},
        inputs={"prompt": "hello"},
    )


@pytest.fixture
def sample_span(sample_trace: Trace) -> Span:
    return Span(
        trace_id=sample_trace.trace_id,
        name="llm-call",
        kind=SpanKind.LLM_CALL,
        status=SpanStatus.OK,
        inputs={"messages": [{"role": "user", "content": "hello"}]},
        metadata={"gen_ai.request.model": "gpt-4o"},
    )


# ---------------------------------------------------------------------------
# Dashboard route
# ---------------------------------------------------------------------------


class TestDashboardRoute:
    async def test_get_root_returns_200(self, client: AsyncClient) -> None:
        res = await client.get("/")
        assert res.status_code == 200

    async def test_get_root_returns_html(self, client: AsyncClient) -> None:
        res = await client.get("/")
        assert "text/html" in res.headers["content-type"]

    async def test_get_root_contains_traceai(self, client: AsyncClient) -> None:
        res = await client.get("/")
        assert "TraceAI" in res.text


# ---------------------------------------------------------------------------
# GET /api/traces
# ---------------------------------------------------------------------------


class TestListTracesEndpoint:
    async def test_list_empty_returns_empty_list(self, client: AsyncClient) -> None:
        res = await client.get("/api/traces")
        assert res.status_code == 200
        data = res.json()
        assert data["traces"] == []

    async def test_list_response_schema(self, client: AsyncClient) -> None:
        res = await client.get("/api/traces")
        data = res.json()
        assert "traces" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    async def test_list_total_reflects_full_count(
        self, client: AsyncClient, store: TraceStore
    ) -> None:
        for i in range(7):
            await store.save_trace(Trace(name=f"trace-{i}", status=SpanStatus.OK))
        res = await client.get("/api/traces?limit=3")
        data = res.json()
        assert len(data["traces"]) == 3
        assert data["total"] == 7

    async def test_list_total_respects_filters(
        self, client: AsyncClient, store: TraceStore
    ) -> None:
        for i in range(4):
            await store.save_trace(Trace(name=f"ok-{i}", status=SpanStatus.OK))
        await store.save_trace(Trace(name="err-0", status=SpanStatus.ERROR))
        res = await client.get("/api/traces?status=ok")
        data = res.json()
        assert data["total"] == 4

    async def test_list_returns_saved_traces(
        self, client: AsyncClient, store: TraceStore, sample_trace: Trace
    ) -> None:
        await store.save_trace(sample_trace)
        res = await client.get("/api/traces")
        assert res.status_code == 200
        data = res.json()
        assert len(data["traces"]) == 1
        assert data["traces"][0]["trace_id"] == sample_trace.trace_id

    async def test_list_limit_param(self, client: AsyncClient, store: TraceStore) -> None:
        for i in range(5):
            await store.save_trace(Trace(name=f"trace-{i}", status=SpanStatus.OK))
        res = await client.get("/api/traces?limit=2")
        assert res.status_code == 200
        assert len(res.json()["traces"]) == 2

    async def test_list_offset_param(self, client: AsyncClient, store: TraceStore) -> None:
        for i in range(5):
            await store.save_trace(Trace(name=f"trace-{i}", status=SpanStatus.OK))
        res_all = await client.get("/api/traces?limit=5")
        res_offset = await client.get("/api/traces?limit=2&offset=2")
        all_ids = [t["trace_id"] for t in res_all.json()["traces"]]
        offset_ids = [t["trace_id"] for t in res_offset.json()["traces"]]
        assert offset_ids == all_ids[2:4]

    async def test_list_filter_by_status_ok(self, client: AsyncClient, store: TraceStore) -> None:
        await store.save_trace(Trace(name="ok-trace", status=SpanStatus.OK))
        await store.save_trace(Trace(name="error-trace", status=SpanStatus.ERROR))
        res = await client.get("/api/traces?status=ok")
        assert res.status_code == 200
        traces = res.json()["traces"]
        assert len(traces) == 1
        assert traces[0]["status"] == "ok"

    async def test_list_filter_by_status_error(
        self, client: AsyncClient, store: TraceStore
    ) -> None:
        await store.save_trace(Trace(name="ok-trace", status=SpanStatus.OK))
        await store.save_trace(Trace(name="error-trace", status=SpanStatus.ERROR))
        res = await client.get("/api/traces?status=error")
        traces = res.json()["traces"]
        assert len(traces) == 1
        assert traces[0]["status"] == "error"

    async def test_list_invalid_status_returns_422(self, client: AsyncClient) -> None:
        res = await client.get("/api/traces?status=bogus")
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/traces/{trace_id}
# ---------------------------------------------------------------------------


class TestGetTraceEndpoint:
    async def test_get_existing_trace_returns_200(
        self, client: AsyncClient, store: TraceStore, sample_trace: Trace
    ) -> None:
        await store.save_trace(sample_trace)
        res = await client.get(f"/api/traces/{sample_trace.trace_id}")
        assert res.status_code == 200

    async def test_get_trace_response_has_correct_fields(
        self, client: AsyncClient, store: TraceStore, sample_trace: Trace
    ) -> None:
        await store.save_trace(sample_trace)
        res = await client.get(f"/api/traces/{sample_trace.trace_id}")
        trace = res.json()["trace"]
        assert trace["trace_id"] == sample_trace.trace_id
        assert trace["name"] == sample_trace.name
        assert trace["status"] == "ok"

    async def test_get_nonexistent_trace_returns_404(self, client: AsyncClient) -> None:
        res = await client.get("/api/traces/doesnotexist")
        assert res.status_code == 404

    async def test_get_trace_with_tags_and_inputs(
        self, client: AsyncClient, store: TraceStore, sample_trace: Trace
    ) -> None:
        await store.save_trace(sample_trace)
        res = await client.get(f"/api/traces/{sample_trace.trace_id}")
        trace = res.json()["trace"]
        assert trace["tags"] == {"env": "test"}
        assert trace["inputs"] == {"prompt": "hello"}


# ---------------------------------------------------------------------------
# GET /api/traces/{trace_id}/spans
# ---------------------------------------------------------------------------


class TestGetSpansEndpoint:
    async def test_get_spans_empty_returns_empty_list(
        self, client: AsyncClient, store: TraceStore, sample_trace: Trace
    ) -> None:
        await store.save_trace(sample_trace)
        res = await client.get(f"/api/traces/{sample_trace.trace_id}/spans")
        assert res.status_code == 200
        assert res.json()["spans"] == []

    async def test_get_spans_returns_all_spans(
        self,
        client: AsyncClient,
        store: TraceStore,
        sample_trace: Trace,
        sample_span: Span,
    ) -> None:
        await store.save_trace(sample_trace)
        for _ in range(3):
            s = Span(trace_id=sample_trace.trace_id, name="s", kind=SpanKind.CUSTOM)
            await store.save_span(s)
        res = await client.get(f"/api/traces/{sample_trace.trace_id}/spans")
        assert len(res.json()["spans"]) == 3

    async def test_get_spans_for_nonexistent_trace_returns_empty(self, client: AsyncClient) -> None:
        res = await client.get("/api/traces/nonexistent/spans")
        assert res.status_code == 200
        assert res.json()["spans"] == []

    async def test_get_spans_with_error_field(
        self, client: AsyncClient, store: TraceStore, sample_trace: Trace
    ) -> None:
        await store.save_trace(sample_trace)
        span = Span(
            trace_id=sample_trace.trace_id,
            name="failing-span",
            kind=SpanKind.TOOL_CALL,
            status=SpanStatus.ERROR,
            error=ErrorDetail(exception_type="ValueError", message="bad input"),
        )
        await store.save_span(span)
        res = await client.get(f"/api/traces/{sample_trace.trace_id}/spans")
        spans = res.json()["spans"]
        assert len(spans) == 1
        assert spans[0]["error"]["exception_type"] == "ValueError"
        assert spans[0]["error"]["message"] == "bad input"

    async def test_get_spans_include_all_kinds(
        self, client: AsyncClient, store: TraceStore, sample_trace: Trace
    ) -> None:
        await store.save_trace(sample_trace)
        for kind in SpanKind:
            await store.save_span(Span(trace_id=sample_trace.trace_id, name=kind.value, kind=kind))
        res = await client.get(f"/api/traces/{sample_trace.trace_id}/spans")
        returned_kinds = {s["kind"] for s in res.json()["spans"]}
        assert returned_kinds == {k.value for k in SpanKind}


# ---------------------------------------------------------------------------
# GET /api/traces?q= (server-side search)
# ---------------------------------------------------------------------------


class TestSearchParam:
    async def test_q_filters_by_name(self, client: AsyncClient, store: TraceStore) -> None:
        await store.save_trace(Trace(name="research-agent", status=SpanStatus.OK))
        await store.save_trace(Trace(name="summarize-agent", status=SpanStatus.OK))
        res = await client.get("/api/traces?q=research")
        assert res.status_code == 200
        traces = res.json()["traces"]
        assert len(traces) == 1
        assert traces[0]["name"] == "research-agent"

    async def test_q_empty_string_returns_all(self, client: AsyncClient, store: TraceStore) -> None:
        for i in range(3):
            await store.save_trace(Trace(name=f"agent-{i}", status=SpanStatus.OK))
        res = await client.get("/api/traces?q=")
        assert res.status_code == 200
        assert len(res.json()["traces"]) == 3

    async def test_q_no_match_returns_empty_list(
        self, client: AsyncClient, store: TraceStore
    ) -> None:
        await store.save_trace(Trace(name="research-agent", status=SpanStatus.OK))
        res = await client.get("/api/traces?q=zzznomatch")
        assert res.status_code == 200
        assert res.json()["traces"] == []


# ---------------------------------------------------------------------------
# POST /api/spans/{span_id}/replay
# ---------------------------------------------------------------------------

_MOCK_RESULT = {
    "content": "Paris",
    "finish_reason": "stop",
    "input_tokens": 10,
    "output_tokens": 5,
    "model": "gpt-4o",
    "system": "openai",
}


class TestReplaySpan:
    @pytest.fixture
    async def saved_llm_span(
        self, store: TraceStore, sample_trace: Trace, sample_span: Span
    ) -> Span:
        await store.save_trace(sample_trace)
        sample_span.close(status=SpanStatus.OK)
        sample_span.metadata = {"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o"}
        await store.save_span(sample_span)
        return sample_span

    @pytest.fixture
    async def saved_non_llm_span(self, store: TraceStore, sample_trace: Trace) -> Span:
        await store.save_trace(sample_trace)
        span = Span(
            trace_id=sample_trace.trace_id,
            name="tool",
            kind=SpanKind.TOOL_CALL,
            status=SpanStatus.OK,
        )
        span.close(status=SpanStatus.OK)
        await store.save_span(span)
        return span

    async def test_replay_returns_trace_and_span_ids(
        self, client: AsyncClient, saved_llm_span: Span
    ) -> None:
        from unittest.mock import AsyncMock, patch

        mock = AsyncMock(return_value=_MOCK_RESULT)
        with patch("traceai.server._replay_openai_compat", new=mock):
            res = await client.post(f"/api/spans/{saved_llm_span.span_id}/replay", json={})
        assert res.status_code == 200
        body = res.json()
        assert "trace_id" in body
        assert "span_id" in body

    async def test_replay_404_for_missing_span(self, client: AsyncClient) -> None:
        res = await client.post("/api/spans/doesnotexist/replay", json={})
        assert res.status_code == 404

    async def test_replay_422_for_non_llm_span(
        self, client: AsyncClient, saved_non_llm_span: Span
    ) -> None:
        res = await client.post(f"/api/spans/{saved_non_llm_span.span_id}/replay", json={})
        assert res.status_code == 422

    async def test_replay_uses_messages_override(
        self, client: AsyncClient, saved_llm_span: Span
    ) -> None:
        from unittest.mock import patch

        override = [{"role": "user", "content": "What is 2+2?"}]
        captured: list[list] = []

        async def mock_replay(messages: list, model: str, provider: str) -> dict:
            captured.append(messages)
            return _MOCK_RESULT

        with patch("traceai.server._replay_openai_compat", new=mock_replay):
            res = await client.post(
                f"/api/spans/{saved_llm_span.span_id}/replay",
                json={"messages": override},
            )
        assert res.status_code == 200
        assert captured[0] == override

    async def test_replay_uses_model_override(
        self, client: AsyncClient, saved_llm_span: Span
    ) -> None:
        from unittest.mock import patch

        captured_models: list[str] = []

        async def mock_replay(messages: list, model: str, provider: str) -> dict:
            captured_models.append(model)
            return _MOCK_RESULT

        with patch("traceai.server._replay_openai_compat", new=mock_replay):
            res = await client.post(
                f"/api/spans/{saved_llm_span.span_id}/replay",
                json={"model": "gpt-4o-mini"},
            )
        assert res.status_code == 200
        assert captured_models[0] == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# POST /api/traces/{trace_id}/replay  (trace-level cascade / model arbitrage)
# ---------------------------------------------------------------------------


class TestReplayTrace:
    @pytest.fixture
    async def saved_trace_with_llm_spans(self, store: TraceStore) -> Trace:
        trace = Trace(
            name="multi-step-agent",
            status=SpanStatus.OK,
            total_tokens=200,
            total_cost_usd=0.05,
            llm_call_count=2,
        )
        await store.save_trace(trace)
        for i in range(2):
            s = Span(
                trace_id=trace.trace_id,
                name=f"llm-step-{i}",
                kind=SpanKind.LLM_CALL,
                status=SpanStatus.OK,
                inputs={"messages": [{"role": "user", "content": f"step {i}"}]},
                metadata={"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o"},
            )
            await store.save_span(s)
        return trace

    @pytest.fixture
    async def saved_trace_no_llm(self, store: TraceStore) -> Trace:
        trace = Trace(name="no-llm-agent", status=SpanStatus.OK)
        await store.save_trace(trace)
        s = Span(
            trace_id=trace.trace_id,
            name="tool-only",
            kind=SpanKind.TOOL_CALL,
            status=SpanStatus.OK,
        )
        await store.save_span(s)
        return trace

    async def test_replay_trace_returns_comparison_stats(
        self, client: AsyncClient, saved_trace_with_llm_spans: Trace
    ) -> None:
        from unittest.mock import AsyncMock, patch

        mock = AsyncMock(return_value=_MOCK_RESULT)
        with patch("traceai.server._replay_openai_compat", new=mock):
            res = await client.post(
                f"/api/traces/{saved_trace_with_llm_spans.trace_id}/replay",
                json={"model": "gpt-4o-mini"},
            )
        assert res.status_code == 200
        body = res.json()
        assert body["spans_replayed"] == 2
        assert "trace_id" in body
        assert "replay_cost_usd" in body
        assert "original_cost_usd" in body

    async def test_replay_trace_404_for_missing_trace(self, client: AsyncClient) -> None:
        res = await client.post("/api/traces/doesnotexist/replay", json={"model": "gpt-4o-mini"})
        assert res.status_code == 404

    async def test_replay_trace_422_for_no_llm_spans(
        self, client: AsyncClient, saved_trace_no_llm: Trace
    ) -> None:
        res = await client.post(
            f"/api/traces/{saved_trace_no_llm.trace_id}/replay",
            json={"model": "gpt-4o-mini"},
        )
        assert res.status_code == 422

    async def test_replay_trace_saves_linked_trace_in_db(
        self, client: AsyncClient, store: TraceStore, saved_trace_with_llm_spans: Trace
    ) -> None:
        from unittest.mock import AsyncMock, patch

        mock = AsyncMock(return_value=_MOCK_RESULT)
        with patch("traceai.server._replay_openai_compat", new=mock):
            res = await client.post(
                f"/api/traces/{saved_trace_with_llm_spans.trace_id}/replay",
                json={"model": "gpt-4o-mini"},
            )
        new_trace_id = res.json()["trace_id"]
        saved = await store.aget_trace(new_trace_id)
        assert saved is not None
        assert saved.tags.get("replay_of_trace") == saved_trace_with_llm_spans.trace_id

    async def test_replay_trace_sets_replay_root(
        self, client: AsyncClient, store: TraceStore, saved_trace_with_llm_spans: Trace
    ) -> None:
        """replay_root should point to the ultimate original trace."""
        from unittest.mock import AsyncMock, patch

        original_id = saved_trace_with_llm_spans.trace_id
        mock = AsyncMock(return_value=_MOCK_RESULT)
        with patch("traceai.server._replay_openai_compat", new=mock):
            res = await client.post(
                f"/api/traces/{original_id}/replay",
                json={"model": "gpt-4o-mini"},
            )
        saved = await store.aget_trace(res.json()["trace_id"])
        assert saved is not None
        assert saved.tags.get("replay_root") == original_id

    async def test_replay_chain_preserves_root(
        self, client: AsyncClient, store: TraceStore, saved_trace_with_llm_spans: Trace
    ) -> None:
        """Replaying a replay should keep the original root, not the intermediate."""
        from unittest.mock import AsyncMock, patch

        original_id = saved_trace_with_llm_spans.trace_id
        mock = AsyncMock(return_value=_MOCK_RESULT)
        with patch("traceai.server._replay_openai_compat", new=mock):
            # First replay
            res1 = await client.post(
                f"/api/traces/{original_id}/replay",
                json={"model": "gpt-4o-mini"},
            )
            mid_id = res1.json()["trace_id"]
            # Second replay (replay of replay)
            res2 = await client.post(
                f"/api/traces/{mid_id}/replay",
                json={"model": "gpt-4o-mini"},
            )
        saved = await store.aget_trace(res2.json()["trace_id"])
        assert saved is not None
        # Should point back to the original, not the intermediate
        assert saved.tags.get("replay_root") == original_id

    async def test_replay_trace_preserves_full_span_structure(
        self, client: AsyncClient, store: TraceStore
    ) -> None:
        """Replayed trace must contain all span kinds, not just llm_call."""
        from unittest.mock import AsyncMock, patch

        trace = Trace(name="structured-agent", status=SpanStatus.OK)
        await store.save_trace(trace)
        agent = Span(trace_id=trace.trace_id, name="agent", kind=SpanKind.AGENT_STEP)
        await store.save_span(agent)
        tool = Span(
            trace_id=trace.trace_id, name="tool", kind=SpanKind.TOOL_CALL,
            parent_span_id=agent.span_id,
        )
        await store.save_span(tool)
        llm = Span(
            trace_id=trace.trace_id, name="llm", kind=SpanKind.LLM_CALL,
            parent_span_id=tool.span_id,
            inputs={"messages": [{"role": "user", "content": "hi"}]},
            metadata={"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o"},
        )
        await store.save_span(llm)

        mock = AsyncMock(return_value=_MOCK_RESULT)
        with patch("traceai.server._replay_openai_compat", new=mock):
            res = await client.post(
                f"/api/traces/{trace.trace_id}/replay",
                json={"model": "gpt-4o-mini"},
            )
        assert res.status_code == 200
        new_trace_id = res.json()["trace_id"]
        new_spans = await store.aget_spans(new_trace_id)
        kinds = {s.kind for s in new_spans}
        assert SpanKind.LLM_CALL in kinds
        assert SpanKind.AGENT_STEP in kinds
        assert SpanKind.TOOL_CALL in kinds
        assert len(new_spans) == 3


# ---------------------------------------------------------------------------
# _infer_provider (unit tests)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET /api/providers
# ---------------------------------------------------------------------------


class TestGetProviders:
    async def test_returns_provider_keys_from_env(self, client: AsyncClient) -> None:
        import os
        from unittest.mock import patch

        import traceai.server

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test", "ANTHROPIC_API_KEY": ""}),
            patch.object(traceai.server, "_CONFIG_PATH", Path("/tmp/nonexistent.toml")),
        ):
            res = await client.get("/api/providers")
        assert res.status_code == 200
        body = res.json()
        assert body["openai"] is True
        assert body["anthropic"] is False

    async def test_missing_keys_return_false(self, client: AsyncClient) -> None:
        import os
        from unittest.mock import patch

        import traceai.server

        _skip = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
        env = {k: v for k, v in os.environ.items() if k not in _skip}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(traceai.server, "_CONFIG_PATH", Path("/tmp/nonexistent.toml")),
        ):
            res = await client.get("/api/providers")
        assert res.status_code == 200
        body = res.json()
        assert body["openai"] is False
        assert body["anthropic"] is False


# ---------------------------------------------------------------------------
# POST /api/keys — key management
# ---------------------------------------------------------------------------


class TestKeyManagement:
    async def test_set_and_get_key(self, client: AsyncClient, tmp_path: Path) -> None:
        import os
        from unittest.mock import patch

        import traceai.server

        config_path = tmp_path / "config.toml"
        _skip = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
        env = {k: v for k, v in os.environ.items() if k not in _skip}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(traceai.server, "_CONFIG_PATH", config_path),
        ):
            # Initially not set
            res = await client.get("/api/keys")
            assert res.status_code == 200
            keys = {k["provider"]: k for k in res.json()}
            assert keys["openai"]["is_set"] is False

            # Save a key
            res = await client.post("/api/keys", json={"provider": "openai", "key": "sk-test123"})
            assert res.status_code == 200

            # Now it should show as configured from config
            res = await client.get("/api/keys")
            keys = {k["provider"]: k for k in res.json()}
            assert keys["openai"]["is_set"] is True
            assert keys["openai"]["source"] == "config"

    async def test_set_key_accepts_any_provider(self, client: AsyncClient, tmp_path: Path) -> None:
        from unittest.mock import patch

        import traceai.server

        config_path = tmp_path / "config.toml"
        with patch.object(traceai.server, "_CONFIG_PATH", config_path):
            res = await client.post("/api/keys", json={"provider": "mistral", "key": "test-key"})
        assert res.status_code == 200
        assert res.json()["provider"] == "mistral"

    async def test_set_key_empty_value(self, client: AsyncClient) -> None:
        res = await client.post("/api/keys", json={"provider": "openai", "key": ""})
        assert res.status_code == 422

    async def test_providers_detects_config_key(self, client: AsyncClient, tmp_path: Path) -> None:
        import os
        from unittest.mock import patch

        import traceai.server

        config_path = tmp_path / "config.toml"
        _skip = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
        env = {k: v for k, v in os.environ.items() if k not in _skip}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(traceai.server, "_CONFIG_PATH", config_path),
        ):
            # Save key via API
            await client.post("/api/keys", json={"provider": "openai", "key": "sk-test"})

            # /api/providers should now show openai as available
            res = await client.get("/api/providers")
            body = res.json()
            assert body["openai"] is True
            assert body["anthropic"] is False

    async def test_delete_key_removes_from_config(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        import os
        from unittest.mock import patch

        import traceai.server

        config_path = tmp_path / "config.toml"
        _skip = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
        env = {k: v for k, v in os.environ.items() if k not in _skip}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(traceai.server, "_CONFIG_PATH", config_path),
        ):
            # Save then delete
            await client.post("/api/keys", json={"provider": "openai", "key": "sk-test"})
            res = await client.delete("/api/keys/openai")
            assert res.status_code == 200

            # Key should no longer be set
            res = await client.get("/api/keys")
            keys = {k["provider"]: k for k in res.json()}
            assert keys["openai"]["is_set"] is False

    async def test_delete_key_accepts_any_provider(self, client: AsyncClient) -> None:
        res = await client.delete("/api/keys/customprovider")
        assert res.status_code == 200

    async def test_delete_key_nonexistent_is_ok(self, client: AsyncClient, tmp_path: Path) -> None:
        import os
        from unittest.mock import patch

        import traceai.server

        config_path = tmp_path / "nonexistent_dir" / "config.toml"
        _skip = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
        env = {k: v for k, v in os.environ.items() if k not in _skip}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(traceai.server, "_CONFIG_PATH", config_path),
        ):
            # Deleting when no config exists should not error
            res = await client.delete("/api/keys/openai")
            assert res.status_code == 200


# ---------------------------------------------------------------------------
# TestReplaySpan — span replay now includes comparison metadata
# ---------------------------------------------------------------------------


class TestReplaySpanComparison:
    @pytest.fixture
    async def saved_llm_span_with_cost(self, store: TraceStore, sample_trace: Trace) -> Span:
        await store.save_trace(sample_trace)
        span = Span(
            trace_id=sample_trace.trace_id,
            name="llm-call",
            kind=SpanKind.LLM_CALL,
            status=SpanStatus.OK,
            inputs={"messages": [{"role": "user", "content": "hello"}]},
            metadata={
                "gen_ai.system": "openai",
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.usage.input_tokens": 10,
                "gen_ai.usage.output_tokens": 5,
                "gen_ai.usage.call_cost_usd": 0.001,
            },
        )
        await store.save_span(span)
        return span

    async def test_span_replay_includes_comparison_metadata(
        self, client: AsyncClient, store: TraceStore, saved_llm_span_with_cost: Span
    ) -> None:
        from unittest.mock import AsyncMock, patch

        mock = AsyncMock(return_value=_MOCK_RESULT)
        with patch("traceai.server._replay_openai_compat", new=mock):
            res = await client.post(
                f"/api/spans/{saved_llm_span_with_cost.span_id}/replay", json={}
            )
        assert res.status_code == 200
        new_trace_id = res.json()["trace_id"]
        saved = await store.aget_trace(new_trace_id)
        assert saved is not None
        assert saved.metadata is not None
        assert "replay_of_trace" in saved.metadata
        assert saved.metadata["original_model"] == "gpt-4o"
        assert saved.metadata["replay_model"] == "gpt-4o"  # same model (mock returns gpt-4o)
        assert saved.tags.get("replay_of_trace") == saved_llm_span_with_cost.trace_id

    async def test_span_replay_tags_use_replay_of_trace_key(
        self, client: AsyncClient, store: TraceStore, saved_llm_span_with_cost: Span
    ) -> None:
        from unittest.mock import AsyncMock, patch

        mock = AsyncMock(return_value=_MOCK_RESULT)
        with patch("traceai.server._replay_openai_compat", new=mock):
            res = await client.post(
                f"/api/spans/{saved_llm_span_with_cost.span_id}/replay", json={}
            )
        new_trace_id = res.json()["trace_id"]
        saved = await store.aget_trace(new_trace_id)
        assert saved is not None
        # Old "replay_of" key should NOT be present; use "replay_of_trace" consistently
        assert "replay_of" not in saved.tags
        assert "replay_of_trace" in saved.tags

    async def test_span_replay_sets_replay_root(
        self, client: AsyncClient, store: TraceStore, saved_llm_span_with_cost: Span
    ) -> None:
        """replay_root should point to the ultimate original trace."""
        from unittest.mock import AsyncMock, patch

        original_trace_id = saved_llm_span_with_cost.trace_id
        mock = AsyncMock(return_value=_MOCK_RESULT)
        with patch("traceai.server._replay_openai_compat", new=mock):
            res = await client.post(
                f"/api/spans/{saved_llm_span_with_cost.span_id}/replay", json={}
            )
        saved = await store.aget_trace(res.json()["trace_id"])
        assert saved is not None
        assert saved.tags.get("replay_root") == original_trace_id


class TestInferProvider:
    def test_claude_model_returns_anthropic(self) -> None:
        from traceai.server import _infer_provider

        assert _infer_provider("claude-sonnet-4-6") == "anthropic"
        assert _infer_provider("claude-haiku-4-5-20251001") == "anthropic"
        assert _infer_provider("claude-opus-4-6") == "anthropic"

    def test_gpt_model_returns_openai(self) -> None:
        from traceai.server import _infer_provider

        assert _infer_provider("gpt-4o") == "openai"
        assert _infer_provider("gpt-4o-mini") == "openai"
        assert _infer_provider("o3-mini") == "openai"

    def test_mistral_model_returns_mistral(self) -> None:
        from traceai.server import _infer_provider

        assert _infer_provider("mistral-large-latest") == "mistral"
        assert _infer_provider("open-mistral-nemo") == "mistral"
        assert _infer_provider("codestral-latest") == "mistral"

    def test_deepseek_model_returns_deepseek(self) -> None:
        from traceai.server import _infer_provider

        assert _infer_provider("deepseek-chat") == "deepseek"
        assert _infer_provider("deepseek-reasoner") == "deepseek"

    def test_perplexity_model_returns_perplexity(self) -> None:
        from traceai.server import _infer_provider

        assert _infer_provider("sonar-pro") == "perplexity"
        assert _infer_provider("sonar-reasoning-pro") == "perplexity"

    def test_unknown_model_defaults_to_openai(self) -> None:
        from traceai.server import _infer_provider

        assert _infer_provider("some-random-model") == "openai"


# ---------------------------------------------------------------------------
# DELETE /api/traces  (clear all data)
# ---------------------------------------------------------------------------


class TestClearAllTraces:
    async def test_clear_returns_deleted_count(
        self, client: AsyncClient, store: TraceStore
    ) -> None:
        for i in range(3):
            await store.save_trace(Trace(name=f"t-{i}", status=SpanStatus.OK))
        res = await client.delete("/api/traces")
        assert res.status_code == 200
        assert res.json()["deleted"] == 3

    async def test_clear_empties_trace_list(
        self, client: AsyncClient, store: TraceStore
    ) -> None:
        await store.save_trace(Trace(name="t", status=SpanStatus.OK))
        await client.delete("/api/traces")
        res = await client.get("/api/traces")
        assert res.json()["traces"] == []
        assert res.json()["total"] == 0

    async def test_clear_empty_db_returns_zero(self, client: AsyncClient) -> None:
        res = await client.delete("/api/traces")
        assert res.status_code == 200
        assert res.json()["deleted"] == 0


# ---------------------------------------------------------------------------
# GET /api/models
# ---------------------------------------------------------------------------


class TestGetModels:
    async def test_returns_curated_models(self, client: AsyncClient) -> None:
        res = await client.get("/api/models")
        assert res.status_code == 200
        body = res.json()
        assert "openai" in body
        assert "anthropic" in body
        assert len(body["openai"]) > 0
        assert "gpt-4o" in body["openai"]

    async def test_includes_multiple_providers(self, client: AsyncClient) -> None:
        res = await client.get("/api/models")
        body = res.json()
        assert "mistral" in body
        assert "deepseek" in body
        assert "groq" in body


# ---------------------------------------------------------------------------
# Custom provider key management (provider-agnostic)
# ---------------------------------------------------------------------------


class TestCustomProviderKeys:
    async def test_save_and_retrieve_custom_provider(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        import os
        from unittest.mock import patch

        import traceai.server

        config_path = tmp_path / "config.toml"
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(traceai.server, "_CONFIG_PATH", config_path),
        ):
            res = await client.post("/api/keys", json={"provider": "cohere", "key": "co-test"})
            assert res.status_code == 200

            # Key should appear in /api/keys listing
            res = await client.get("/api/keys")
            keys = {k["provider"]: k for k in res.json()}
            assert "cohere" in keys
            assert keys["cohere"]["is_set"] is True
            assert keys["cohere"]["source"] == "config"

    async def test_custom_provider_appears_in_providers(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        import os
        from unittest.mock import patch

        import traceai.server

        config_path = tmp_path / "config.toml"
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(traceai.server, "_CONFIG_PATH", config_path),
        ):
            await client.post("/api/keys", json={"provider": "cohere", "key": "co-test"})
            res = await client.get("/api/providers")
            body = res.json()
            assert "cohere" in body
            assert body["cohere"] is True

    async def test_delete_custom_provider_key(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        import os
        from unittest.mock import patch

        import traceai.server

        config_path = tmp_path / "config.toml"
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(traceai.server, "_CONFIG_PATH", config_path),
        ):
            await client.post("/api/keys", json={"provider": "cohere", "key": "co-test"})
            res = await client.delete("/api/keys/cohere")
            assert res.status_code == 200

            res = await client.get("/api/keys")
            keys = {k["provider"]: k for k in res.json()}
            # cohere may still appear (from config scan) but should not be set
            if "cohere" in keys:
                assert keys["cohere"]["is_set"] is False
