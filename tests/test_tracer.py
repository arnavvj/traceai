"""Tests for traceai.tracer — Tracer, SpanContext, context propagation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from traceai.models import SpanKind, SpanStatus
from traceai.storage import TraceStore
from traceai.tracer import Tracer


@pytest.fixture
def store(tmp_path: Path) -> TraceStore:
    return TraceStore(db_path=tmp_path / "test.db")


@pytest.fixture
def tracer(store: TraceStore) -> Tracer:
    return Tracer(store=store)


# ------------------------------------------------------------------
# @tracer.trace decorator — sync
# ------------------------------------------------------------------


class TestTraceDecoratorSync:
    def test_basic_trace_is_saved(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def agent(prompt: str) -> str:
            return f"answer: {prompt}"

        result = agent("hello")
        assert result == "answer: hello"

        traces = store.list_traces()
        assert len(traces) == 1
        t = traces[0]
        assert t.name == "agent"
        assert t.status == SpanStatus.OK

    def test_trace_captures_inputs(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn(x: int, y: int) -> int:
            return x + y

        fn(3, 4)
        trace = store.list_traces()[0]
        assert trace.inputs == {"x": 3, "y": 4}

    def test_trace_captures_output(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> str:
            return "done"

        fn()
        trace = store.list_traces()[0]
        assert trace.outputs == {"result": "done"}

    def test_trace_custom_name(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace(name="my-agent")
        def fn() -> None:
            pass

        fn()
        trace = store.list_traces()[0]
        assert trace.name == "my-agent"

    def test_trace_custom_tags(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace(tags={"env": "test", "version": "1"})
        def fn() -> None:
            pass

        fn()
        trace = store.list_traces()[0]
        assert trace.tags == {"env": "test", "version": "1"}

    def test_trace_error_status_on_exception(
        self, tracer: Tracer, store: TraceStore
    ) -> None:
        @tracer.trace
        def failing_agent() -> None:
            raise ValueError("something broke")

        with pytest.raises(ValueError, match="something broke"):
            failing_agent()

        trace = store.list_traces()[0]
        assert trace.status == SpanStatus.ERROR

    def test_exception_propagates(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            fn()

    def test_trace_timing(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            pass

        fn()
        trace = store.list_traces()[0]
        assert trace.started_at is not None
        assert trace.ended_at is not None
        assert trace.duration_ms is not None
        assert trace.duration_ms >= 0


# ------------------------------------------------------------------
# @tracer.trace decorator — async
# ------------------------------------------------------------------


class TestTraceDecoratorAsync:
    @pytest.mark.asyncio
    async def test_async_trace_is_saved(
        self, tracer: Tracer, store: TraceStore
    ) -> None:
        @tracer.trace
        async def agent(prompt: str) -> str:
            return f"async: {prompt}"

        result = await agent("hello")
        assert result == "async: hello"

        traces = store.list_traces()
        assert len(traces) == 1
        assert traces[0].status == SpanStatus.OK

    @pytest.mark.asyncio
    async def test_async_trace_captures_inputs(
        self, tracer: Tracer, store: TraceStore
    ) -> None:
        @tracer.trace
        async def fn(x: int) -> int:
            return x * 2

        await fn(5)
        trace = store.list_traces()[0]
        assert trace.inputs == {"x": 5}

    @pytest.mark.asyncio
    async def test_async_trace_error_on_exception(
        self, tracer: Tracer, store: TraceStore
    ) -> None:
        @tracer.trace
        async def fn() -> None:
            raise TypeError("async fail")

        with pytest.raises(TypeError):
            await fn()

        trace = store.list_traces()[0]
        assert trace.status == SpanStatus.ERROR

    @pytest.mark.asyncio
    async def test_concurrent_traces_do_not_bleed(
        self, tracer: Tracer, store: TraceStore
    ) -> None:
        """Two concurrent agent runs must not share ContextVar state."""

        @tracer.trace
        async def agent(name: str) -> str:
            await asyncio.sleep(0)  # yield to let other task run
            return name

        results = await asyncio.gather(agent("alpha"), agent("beta"))
        assert set(results) == {"alpha", "beta"}

        traces = store.list_traces()
        assert len(traces) == 2
        # Both traces must be OK
        assert all(t.status == SpanStatus.OK for t in traces)


# ------------------------------------------------------------------
# tracer.span() context manager — sync
# ------------------------------------------------------------------


class TestSpanContextManagerSync:
    def test_span_is_saved(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            with tracer.span("step") as span:
                span.set_input({"x": 1})
                span.set_output({"y": 2})

        fn()
        traces = store.list_traces()
        assert len(traces) == 1
        spans = store.get_spans(traces[0].trace_id)
        assert len(spans) == 1
        s = spans[0]
        assert s.name == "step"
        assert s.inputs == {"x": 1}
        assert s.outputs == {"y": 2}
        assert s.status == SpanStatus.OK

    def test_span_kind(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            with tracer.span("llm", kind=SpanKind.LLM_CALL):
                pass

        fn()
        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].kind == SpanKind.LLM_CALL

    def test_span_kind_as_string(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            with tracer.span("tool", kind="tool_call"):
                pass

        fn()
        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].kind == SpanKind.TOOL_CALL

    def test_span_error_captured(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            with tracer.span("bad-step"):
                raise ValueError("span error")

        with pytest.raises(ValueError):
            fn()

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert len(spans) == 1
        s = spans[0]
        assert s.status == SpanStatus.ERROR
        assert s.error is not None
        assert s.error.exception_type == "ValueError"
        assert "span error" in s.error.message

    def test_nested_spans_parent_child(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            with tracer.span("outer") as outer:
                with tracer.span("inner") as inner:
                    pass

        fn()
        trace = store.list_traces()[0]
        spans = store.get_spans(trace.trace_id)
        assert len(spans) == 2

        outer = next(s for s in spans if s.name == "outer")
        inner = next(s for s in spans if s.name == "inner")
        assert inner.parent_span_id == outer.span_id
        assert outer.parent_span_id is None

    def test_multiple_sequential_spans(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            with tracer.span("step-1"):
                pass
            with tracer.span("step-2"):
                pass

        fn()
        trace = store.list_traces()[0]
        spans = store.get_spans(trace.trace_id)
        assert len(spans) == 2
        names = {s.name for s in spans}
        assert names == {"step-1", "step-2"}

    def test_span_metadata(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            with tracer.span("llm", metadata={"gen_ai.request.model": "gpt-4o"}) as s:
                s.set_metadata({"gen_ai.usage.input_tokens": 42})

        fn()
        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].metadata == {
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.usage.input_tokens": 42,
        }

    def test_span_timing(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            with tracer.span("step"):
                pass

        fn()
        s = store.get_spans(store.list_traces()[0].trace_id)[0]
        assert s.ended_at is not None
        assert s.duration_ms is not None
        assert s.duration_ms >= 0


# ------------------------------------------------------------------
# tracer.span() context manager — async
# ------------------------------------------------------------------


class TestSpanContextManagerAsync:
    @pytest.mark.asyncio
    async def test_async_span_is_saved(
        self, tracer: Tracer, store: TraceStore
    ) -> None:
        @tracer.trace
        async def fn() -> None:
            async with tracer.span("async-step") as span:
                span.set_input({"q": "hello"})

        await fn()
        trace = store.list_traces()[0]
        spans = store.get_spans(trace.trace_id)
        assert len(spans) == 1
        assert spans[0].name == "async-step"
        assert spans[0].inputs == {"q": "hello"}

    @pytest.mark.asyncio
    async def test_async_nested_spans(
        self, tracer: Tracer, store: TraceStore
    ) -> None:
        @tracer.trace
        async def fn() -> None:
            async with tracer.span("outer") as outer:
                async with tracer.span("inner") as inner:
                    pass

        await fn()
        trace = store.list_traces()[0]
        spans = store.get_spans(trace.trace_id)
        assert len(spans) == 2
        outer = next(s for s in spans if s.name == "outer")
        inner = next(s for s in spans if s.name == "inner")
        assert inner.parent_span_id == outer.span_id

    @pytest.mark.asyncio
    async def test_async_span_error(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        async def fn() -> None:
            async with tracer.span("failing"):
                raise RuntimeError("async span error")

        with pytest.raises(RuntimeError):
            await fn()

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].status == SpanStatus.ERROR
        assert spans[0].error is not None


# ------------------------------------------------------------------
# SpanContext methods
# ------------------------------------------------------------------


class TestSpanContext:
    def test_set_input(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            with tracer.span("s") as span:
                span.set_input({"prompt": "hi"})

        fn()
        s = store.get_spans(store.list_traces()[0].trace_id)[0]
        assert s.inputs == {"prompt": "hi"}

    def test_set_output(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            with tracer.span("s") as span:
                span.set_output({"response": "hello"})

        fn()
        s = store.get_spans(store.list_traces()[0].trace_id)[0]
        assert s.outputs == {"response": "hello"}

    def test_set_metadata_merges(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            with tracer.span("s") as span:
                span.set_metadata({"a": 1})
                span.set_metadata({"b": 2})

        fn()
        s = store.get_spans(store.list_traces()[0].trace_id)[0]
        assert s.metadata is not None
        assert s.metadata["a"] == 1
        assert s.metadata["b"] == 2

    def test_record_error(self, tracer: Tracer, store: TraceStore) -> None:
        @tracer.trace
        def fn() -> None:
            with tracer.span("s") as span:
                try:
                    raise KeyError("missing key")
                except KeyError as exc:
                    span.record_error(exc)

        fn()
        s = store.get_spans(store.list_traces()[0].trace_id)[0]
        assert s.status == SpanStatus.ERROR
        assert s.error is not None
        assert s.error.exception_type == "KeyError"

    def test_span_id_and_trace_id_accessible(
        self, tracer: Tracer, store: TraceStore
    ) -> None:
        captured: dict = {}

        @tracer.trace
        def fn() -> None:
            with tracer.span("s") as span:
                captured["span_id"] = span.span_id
                captured["trace_id"] = span.trace_id

        fn()
        assert captured["span_id"]
        assert captured["trace_id"]
        trace = store.list_traces()[0]
        assert captured["trace_id"] == trace.trace_id


# ------------------------------------------------------------------
# Context accessors
# ------------------------------------------------------------------


class TestContextAccessors:
    def test_current_trace_id_inside_trace(
        self, tracer: Tracer, store: TraceStore
    ) -> None:
        captured: dict = {}

        @tracer.trace
        def fn() -> None:
            captured["trace_id"] = tracer.current_trace_id()

        fn()
        assert captured["trace_id"] is not None
        trace = store.list_traces()[0]
        assert captured["trace_id"] == trace.trace_id

    def test_current_trace_id_outside_trace(self, tracer: Tracer) -> None:
        assert tracer.current_trace_id() is None

    def test_current_span_id_inside_span(
        self, tracer: Tracer, store: TraceStore
    ) -> None:
        captured: dict = {}

        @tracer.trace
        def fn() -> None:
            with tracer.span("s") as span:
                captured["span_id"] = tracer.current_span_id()
                captured["ctx_span_id"] = span.span_id

        fn()
        assert captured["span_id"] == captured["ctx_span_id"]

    def test_current_span_id_outside_span(self, tracer: Tracer) -> None:
        assert tracer.current_span_id() is None
