"""Tests for traceai.models — Span, Trace, enums, ErrorDetail."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from traceai.models import ErrorDetail, Span, SpanKind, SpanStatus, Trace


class TestSpanKind:
    def test_all_values_are_strings(self) -> None:
        for kind in SpanKind:
            assert isinstance(kind.value, str)

    def test_can_construct_from_string(self) -> None:
        assert SpanKind("llm_call") is SpanKind.LLM_CALL
        assert SpanKind("tool_call") is SpanKind.TOOL_CALL


class TestSpanStatus:
    def test_all_values_are_strings(self) -> None:
        for status in SpanStatus:
            assert isinstance(status.value, str)


class TestErrorDetail:
    def test_from_exception(self) -> None:
        try:
            raise ValueError("something went wrong")
        except ValueError as exc:
            detail = ErrorDetail.from_exception(exc)

        assert detail.exception_type == "ValueError"
        assert detail.message == "something went wrong"
        assert detail.traceback is not None
        assert "ValueError" in detail.traceback

    def test_from_exception_no_traceback_when_not_raised(self) -> None:
        exc = RuntimeError("raw error")
        detail = ErrorDetail.from_exception(exc)
        assert detail.exception_type == "RuntimeError"
        assert detail.message == "raw error"


class TestSpan:
    def test_defaults(self) -> None:
        span = Span(trace_id="abc123", name="test-span")
        assert span.span_id  # non-empty
        assert span.trace_id == "abc123"
        assert span.parent_span_id is None
        assert span.kind is SpanKind.CUSTOM
        assert span.status is SpanStatus.PENDING
        assert span.inputs is None
        assert span.outputs is None
        assert span.error is None
        assert span.ended_at is None
        assert span.duration_ms is None

    def test_span_id_is_unique(self) -> None:
        s1 = Span(trace_id="t1", name="a")
        s2 = Span(trace_id="t1", name="b")
        assert s1.span_id != s2.span_id

    def test_close_sets_timing_and_status(self) -> None:
        span = Span(trace_id="t1", name="step")
        time.sleep(0.01)
        span.close(status=SpanStatus.OK, outputs={"result": 42})

        assert span.ended_at is not None
        assert span.duration_ms is not None
        assert span.duration_ms >= 0
        assert span.status is SpanStatus.OK
        assert span.outputs == {"result": 42}

    def test_close_with_error(self) -> None:
        span = Span(trace_id="t1", name="step")
        err = ErrorDetail(exception_type="ValueError", message="bad input")
        span.close(error=err)

        assert span.status is SpanStatus.ERROR
        assert span.error is not None
        assert span.error.exception_type == "ValueError"

    def test_kind_can_be_set(self) -> None:
        span = Span(trace_id="t1", name="llm", kind=SpanKind.LLM_CALL)
        assert span.kind is SpanKind.LLM_CALL

    def test_started_at_is_utc(self) -> None:
        span = Span(trace_id="t1", name="s")
        assert span.started_at.tzinfo is not None


class TestTrace:
    def test_defaults(self) -> None:
        trace = Trace(name="my-agent")
        assert trace.trace_id
        assert trace.name == "my-agent"
        assert trace.status is SpanStatus.PENDING
        assert trace.span_count == 0
        assert trace.llm_call_count == 0
        assert trace.tags == {}
        assert trace.ended_at is None

    def test_trace_id_is_unique(self) -> None:
        t1 = Trace(name="a")
        t2 = Trace(name="b")
        assert t1.trace_id != t2.trace_id

    def test_close(self) -> None:
        trace = Trace(name="agent")
        time.sleep(0.01)
        trace.close(status=SpanStatus.OK, outputs={"answer": "yes"})

        assert trace.ended_at is not None
        assert trace.duration_ms is not None
        assert trace.duration_ms >= 0
        assert trace.status is SpanStatus.OK
        assert trace.outputs == {"answer": "yes"}

    def test_tags_are_mutable(self) -> None:
        trace = Trace(name="a", tags={"env": "test"})
        assert trace.tags["env"] == "test"

    def test_started_at_is_utc(self) -> None:
        trace = Trace(name="t")
        assert trace.started_at.tzinfo is not None
