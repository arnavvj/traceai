"""Tests for traceai.storage — TraceStore read/write round-trips."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from traceai.models import ErrorDetail, Span, SpanKind, SpanStatus, Trace
from traceai.storage import TraceStore


@pytest.fixture
def store(tmp_path: Path) -> TraceStore:
    """Fresh in-memory-equivalent store backed by a temp file."""
    return TraceStore(db_path=tmp_path / "test.db")


@pytest.fixture
def sample_trace() -> Trace:
    return Trace(
        name="test-agent",
        tags={"env": "test"},
        inputs={"prompt": "hello"},
    )


@pytest.fixture
def sample_span(sample_trace: Trace) -> Span:
    return Span(
        trace_id=sample_trace.trace_id,
        name="llm-call",
        kind=SpanKind.LLM_CALL,
        inputs={"messages": [{"role": "user", "content": "hello"}]},
        metadata={"gen_ai.request.model": "gpt-4o"},
    )


# ------------------------------------------------------------------
# Sync tests
# ------------------------------------------------------------------


class TestSyncTraceStore:
    def test_list_traces_empty(self, store: TraceStore) -> None:
        assert store.list_traces() == []

    def test_get_trace_missing(self, store: TraceStore) -> None:
        assert store.get_trace("nonexistent") is None

    def test_save_and_get_trace(self, store: TraceStore, sample_trace: Trace) -> None:
        asyncio.run(store.save_trace(sample_trace))
        result = store.get_trace(sample_trace.trace_id)

        assert result is not None
        assert result.trace_id == sample_trace.trace_id
        assert result.name == sample_trace.name
        assert result.tags == {"env": "test"}
        assert result.inputs == {"prompt": "hello"}

    def test_list_traces_returns_saved(
        self, store: TraceStore, sample_trace: Trace
    ) -> None:
        asyncio.run(store.save_trace(sample_trace))
        traces = store.list_traces()
        assert len(traces) == 1
        assert traces[0].trace_id == sample_trace.trace_id

    def test_list_traces_limit(self, store: TraceStore) -> None:
        for i in range(5):
            asyncio.run(store.save_trace(Trace(name=f"agent-{i}")))
        assert len(store.list_traces(limit=3)) == 3

    def test_list_traces_filter_by_status(self, store: TraceStore) -> None:
        ok_trace = Trace(name="ok-agent", status=SpanStatus.OK)
        err_trace = Trace(name="err-agent", status=SpanStatus.ERROR)
        asyncio.run(store.save_trace(ok_trace))
        asyncio.run(store.save_trace(err_trace))

        ok_results = store.list_traces(status="ok")
        assert len(ok_results) == 1
        assert ok_results[0].status is SpanStatus.OK

    def test_save_and_get_spans(
        self, store: TraceStore, sample_trace: Trace, sample_span: Span
    ) -> None:
        asyncio.run(store.save_trace(sample_trace))
        asyncio.run(store.save_span(sample_span))

        spans = store.get_spans(sample_trace.trace_id)
        assert len(spans) == 1
        s = spans[0]
        assert s.span_id == sample_span.span_id
        assert s.name == "llm-call"
        assert s.kind is SpanKind.LLM_CALL
        assert s.inputs == {"messages": [{"role": "user", "content": "hello"}]}
        assert s.metadata == {"gen_ai.request.model": "gpt-4o"}

    def test_get_spans_empty(self, store: TraceStore) -> None:
        assert store.get_spans("nonexistent") == []

    def test_span_with_error_round_trips(
        self, store: TraceStore, sample_trace: Trace
    ) -> None:
        span = Span(trace_id=sample_trace.trace_id, name="bad-call")
        err = ErrorDetail(
            exception_type="openai.RateLimitError",
            message="Rate limit exceeded",
            traceback="Traceback ...",
        )
        span.close(error=err)

        asyncio.run(store.save_trace(sample_trace))
        asyncio.run(store.save_span(span))

        result = store.get_spans(sample_trace.trace_id)[0]
        assert result.status is SpanStatus.ERROR
        assert result.error is not None
        assert result.error.exception_type == "openai.RateLimitError"
        assert result.error.traceback == "Traceback ..."

    def test_delete_trace(self, store: TraceStore, sample_trace: Trace) -> None:
        asyncio.run(store.save_trace(sample_trace))
        assert store.get_trace(sample_trace.trace_id) is not None

        deleted = store.delete_trace(sample_trace.trace_id)
        assert deleted is True
        assert store.get_trace(sample_trace.trace_id) is None

    def test_delete_nonexistent_trace(self, store: TraceStore) -> None:
        assert store.delete_trace("ghost") is False

    def test_delete_trace_cascades_spans(
        self, store: TraceStore, sample_trace: Trace, sample_span: Span
    ) -> None:
        asyncio.run(store.save_trace(sample_trace))
        asyncio.run(store.save_span(sample_span))
        assert len(store.get_spans(sample_trace.trace_id)) == 1

        store.delete_trace(sample_trace.trace_id)
        assert store.get_spans(sample_trace.trace_id) == []

    def test_upsert_trace(self, store: TraceStore, sample_trace: Trace) -> None:
        asyncio.run(store.save_trace(sample_trace))
        sample_trace.status = SpanStatus.OK
        sample_trace.span_count = 3
        asyncio.run(store.save_trace(sample_trace))

        result = store.get_trace(sample_trace.trace_id)
        assert result is not None
        assert result.status is SpanStatus.OK
        assert result.span_count == 3


# ------------------------------------------------------------------
# Async tests
# ------------------------------------------------------------------


class TestAsyncTraceStore:
    @pytest.mark.asyncio
    async def test_alist_traces_empty(self, store: TraceStore) -> None:
        assert await store.alist_traces() == []

    @pytest.mark.asyncio
    async def test_save_and_aget_trace(
        self, store: TraceStore, sample_trace: Trace
    ) -> None:
        await store.save_trace(sample_trace)
        result = await store.aget_trace(sample_trace.trace_id)

        assert result is not None
        assert result.trace_id == sample_trace.trace_id
        assert result.name == sample_trace.name

    @pytest.mark.asyncio
    async def test_aget_spans(
        self, store: TraceStore, sample_trace: Trace, sample_span: Span
    ) -> None:
        await store.save_trace(sample_trace)
        await store.save_span(sample_span)
        spans = await store.aget_spans(sample_trace.trace_id)
        assert len(spans) == 1
        assert spans[0].kind is SpanKind.LLM_CALL

    @pytest.mark.asyncio
    async def test_alist_traces_filter_status(self, store: TraceStore) -> None:
        await store.save_trace(Trace(name="ok", status=SpanStatus.OK))
        await store.save_trace(Trace(name="err", status=SpanStatus.ERROR))

        results = await store.alist_traces(status="error")
        assert len(results) == 1
        assert results[0].status is SpanStatus.ERROR

    @pytest.mark.asyncio
    async def test_null_fields_round_trip(self, store: TraceStore) -> None:
        trace = Trace(name="minimal")
        await store.save_trace(trace)
        result = await store.aget_trace(trace.trace_id)

        assert result is not None
        assert result.inputs is None
        assert result.outputs is None
        assert result.metadata is None
        assert result.total_tokens is None
