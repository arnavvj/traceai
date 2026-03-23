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
        assert "limit" in data
        assert "offset" in data

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
