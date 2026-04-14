"""Tests for traceai.integrations.anthropic — Anthropic auto-instrumentation patch."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic.resources.messages as _ant
import pytest

import traceai
import traceai.integrations.anthropic as _ant_module
from traceai.models import SpanKind, SpanStatus
from traceai.storage import TraceStore
from traceai.tracer import Tracer, _current_span_id, _current_trace_id

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_response(
    content: str = "Test response",
    stop_reason: str = "end_turn",
    model: str = "claude-haiku-4-5",
    input_tokens: int = 42,
    output_tokens: int = 128,
) -> MagicMock:
    """Build a realistic fake Anthropic Message MagicMock."""
    response = MagicMock()
    response.model = model
    response.stop_reason = stop_reason
    response.content = [MagicMock()]
    response.content[0].text = content
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> TraceStore:
    return TraceStore(db_path=tmp_path / "test.db")


@pytest.fixture
def isolated_tracer(store: TraceStore) -> Tracer:
    return Tracer(store=store)


@pytest.fixture(autouse=True)
def reset_patch(monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[misc]
    """Restore _patched flag, original class methods, and ContextVars after each test."""
    original_sync = _ant.Messages.create
    original_async = _ant.AsyncMessages.create
    monkeypatch.setattr(_ant_module, "_patched", False)
    yield  # type: ignore[misc]
    _ant.Messages.create = original_sync  # type: ignore[method-assign]
    _ant.AsyncMessages.create = original_async  # type: ignore[method-assign]
    _ant_module._patched = False
    # Reset ContextVars so implicit traces don't leak into later tests.
    _current_trace_id.set(None)
    _current_span_id.set(None)


@pytest.fixture
def patch_global_tracer(isolated_tracer: Tracer, monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap the global traceai.tracer singleton with the test-isolated tracer."""
    monkeypatch.setattr(traceai, "tracer", isolated_tracer)


# ---------------------------------------------------------------------------
# TestInstrumentIdempotency
# ---------------------------------------------------------------------------


class TestInstrumentIdempotency:
    def test_instrument_once_patches_class(self) -> None:
        original = _ant.Messages.create
        _ant_module.instrument()
        assert _ant.Messages.create is not original

    def test_instrument_twice_does_not_double_wrap(self) -> None:
        _ant_module.instrument()
        patched_once = _ant.Messages.create
        _ant_module.instrument()  # second call — must be a no-op
        assert _ant.Messages.create is patched_once


# ---------------------------------------------------------------------------
# TestSyncPatch
# ---------------------------------------------------------------------------


class TestSyncPatch:
    def test_span_created_with_correct_kind(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        fake = _make_fake_response()
        with patch.object(_ant.Messages, "create", return_value=fake):
            _ant_module.instrument()
            _ant.Messages.create(MagicMock(), messages=[], model="claude-haiku-4-5", max_tokens=100)

        traces = store.list_traces()
        assert len(traces) == 1
        spans = store.get_spans(traces[0].trace_id)
        assert len(spans) == 1
        assert spans[0].kind == SpanKind.LLM_CALL

    def test_span_captures_inputs(self, store: TraceStore, patch_global_tracer: None) -> None:
        fake = _make_fake_response()
        messages = [{"role": "user", "content": "Hello"}]
        with patch.object(_ant.Messages, "create", return_value=fake):
            _ant_module.instrument()
            _ant.Messages.create(
                MagicMock(), messages=messages, model="claude-haiku-4-5", max_tokens=100
            )

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].inputs == {"messages": messages, "model": "claude-haiku-4-5"}

    def test_span_captures_outputs(self, store: TraceStore, patch_global_tracer: None) -> None:
        fake = _make_fake_response(content="Bonjour", stop_reason="end_turn")
        with patch.object(_ant.Messages, "create", return_value=fake):
            _ant_module.instrument()
            _ant.Messages.create(MagicMock(), messages=[], model="claude-haiku-4-5", max_tokens=100)

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].outputs == {"content": "Bonjour", "stop_reason": "end_turn"}

    def test_span_captures_token_metadata(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        fake = _make_fake_response(input_tokens=10, output_tokens=20)
        with patch.object(_ant.Messages, "create", return_value=fake):
            _ant_module.instrument()
            _ant.Messages.create(MagicMock(), messages=[], model="claude-haiku-4-5", max_tokens=100)

        spans = store.get_spans(store.list_traces()[0].trace_id)
        meta = spans[0].metadata
        assert meta is not None
        assert meta["gen_ai.system"] == "anthropic"
        assert meta["gen_ai.request.model"] == "claude-haiku-4-5"
        assert meta["gen_ai.usage.input_tokens"] == 10
        assert meta["gen_ai.usage.output_tokens"] == 20

    def test_span_error_on_exception(self, store: TraceStore, patch_global_tracer: None) -> None:
        with patch.object(_ant.Messages, "create", side_effect=RuntimeError("API error")):
            _ant_module.instrument()
            with pytest.raises(RuntimeError, match="API error"):
                _ant.Messages.create(
                    MagicMock(), messages=[], model="claude-haiku-4-5", max_tokens=100
                )

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].status == SpanStatus.ERROR
        assert spans[0].error is not None
        assert spans[0].error.exception_type == "RuntimeError"
        assert spans[0].error.message == "API error"

    def test_works_outside_trace_creates_implicit_trace(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        """Calling create() without @tracer.trace still produces a trace + span."""
        fake = _make_fake_response()
        with patch.object(_ant.Messages, "create", return_value=fake):
            _ant_module.instrument()
            _ant.Messages.create(MagicMock(), messages=[], model="claude-haiku-4-5", max_tokens=100)

        traces = store.list_traces()
        assert len(traces) >= 1
        spans = store.get_spans(traces[0].trace_id)
        assert len(spans) == 1


# ---------------------------------------------------------------------------
# TestAsyncPatch
# ---------------------------------------------------------------------------


class TestAsyncPatch:
    async def test_async_span_created(self, store: TraceStore, patch_global_tracer: None) -> None:
        fake = _make_fake_response()
        with patch.object(_ant.AsyncMessages, "create", new=AsyncMock(return_value=fake)):
            _ant_module.instrument()
            await _ant.AsyncMessages.create(
                MagicMock(),
                messages=[{"role": "user", "content": "hi"}],
                model="claude-haiku-4-5",
                max_tokens=100,
            )

        await asyncio.sleep(0.05)
        traces = store.list_traces()
        assert len(traces) == 1
        spans = store.get_spans(traces[0].trace_id)
        assert len(spans) == 1
        assert spans[0].kind == SpanKind.LLM_CALL

    async def test_async_span_error_on_exception(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        with patch.object(
            _ant.AsyncMessages,
            "create",
            new=AsyncMock(side_effect=RuntimeError("async API error")),
        ):
            _ant_module.instrument()
            with pytest.raises(RuntimeError, match="async API error"):
                await _ant.AsyncMessages.create(
                    MagicMock(), messages=[], model="claude-haiku-4-5", max_tokens=100
                )

        await asyncio.sleep(0.05)
        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].status == SpanStatus.ERROR
        assert spans[0].error is not None
        assert spans[0].error.message == "async API error"


# ---------------------------------------------------------------------------
# TestContentEdgeCases
# ---------------------------------------------------------------------------


class TestContentEdgeCases:
    def test_empty_content_list_yields_none(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        """When response.content is an empty list, output content should be None."""
        fake = _make_fake_response()
        fake.content = []  # override to empty
        with patch.object(_ant.Messages, "create", return_value=fake):
            _ant_module.instrument()
            _ant.Messages.create(MagicMock(), messages=[], model="claude-haiku-4-5", max_tokens=100)

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].outputs is not None
        assert spans[0].outputs["content"] is None

    def test_non_text_block_yields_none(self, store: TraceStore, patch_global_tracer: None) -> None:
        """Non-text blocks (e.g. tool_use) lack .text — getattr guard yields None."""
        fake = _make_fake_response()
        non_text = MagicMock(spec=[])  # no .text attribute
        fake.content = [non_text]
        with patch.object(_ant.Messages, "create", return_value=fake):
            _ant_module.instrument()
            _ant.Messages.create(MagicMock(), messages=[], model="claude-haiku-4-5", max_tokens=100)

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].outputs is not None
        assert spans[0].outputs["content"] is None


# ---------------------------------------------------------------------------
# Streaming helpers
# ---------------------------------------------------------------------------


def _make_stream_events(
    content_parts: list[str],
    stop_reason: str = "end_turn",
    input_tokens: int | None = 42,
    output_tokens: int | None = 128,
) -> list[MagicMock]:
    """Build a list of fake Anthropic streaming events."""
    events: list[MagicMock] = []
    # message_start with input tokens
    msg_start = MagicMock()
    msg_start.type = "message_start"
    if input_tokens is not None:
        msg_start.message.usage.input_tokens = input_tokens
    else:
        msg_start.message = None
    events.append(msg_start)
    # content_block_delta events
    for part in content_parts:
        delta_event = MagicMock()
        delta_event.type = "content_block_delta"
        delta_event.delta.text = part
        events.append(delta_event)
    # message_delta with output tokens + stop_reason
    msg_delta = MagicMock()
    msg_delta.type = "message_delta"
    msg_delta.delta.stop_reason = stop_reason
    if output_tokens is not None:
        msg_delta.usage.output_tokens = output_tokens
    else:
        msg_delta.usage = None
    events.append(msg_delta)
    # message_stop
    msg_stop = MagicMock()
    msg_stop.type = "message_stop"
    events.append(msg_stop)
    return events


# ---------------------------------------------------------------------------
# TestSyncStreaming
# ---------------------------------------------------------------------------


class TestSyncStreaming:
    def test_streaming_creates_span_with_correct_kind(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        events = _make_stream_events(["Hello", " world"])
        fake_stream = MagicMock()
        fake_stream.__iter__ = MagicMock(return_value=iter(events))
        with patch.object(_ant.Messages, "create", return_value=fake_stream):
            _ant_module.instrument()
            result = _ant.Messages.create(
                MagicMock(),
                messages=[],
                model="claude-haiku-4-5",
                max_tokens=100,
                stream=True,
            )
            list(result)

        traces = store.list_traces()
        assert len(traces) == 1
        spans = store.get_spans(traces[0].trace_id)
        assert len(spans) == 1
        assert spans[0].kind == SpanKind.LLM_CALL

    def test_streaming_captures_accumulated_content(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        events = _make_stream_events(["Hello", " ", "world"])
        fake_stream = MagicMock()
        fake_stream.__iter__ = MagicMock(return_value=iter(events))
        with patch.object(_ant.Messages, "create", return_value=fake_stream):
            _ant_module.instrument()
            result = _ant.Messages.create(
                MagicMock(),
                messages=[],
                model="claude-haiku-4-5",
                max_tokens=100,
                stream=True,
            )
            list(result)

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].outputs is not None
        assert spans[0].outputs["content"] == "Hello world"
        assert spans[0].outputs["stop_reason"] == "end_turn"

    def test_streaming_captures_token_usage(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        events = _make_stream_events(["Hi"], input_tokens=10, output_tokens=5)
        fake_stream = MagicMock()
        fake_stream.__iter__ = MagicMock(return_value=iter(events))
        with patch.object(_ant.Messages, "create", return_value=fake_stream):
            _ant_module.instrument()
            result = _ant.Messages.create(
                MagicMock(),
                messages=[],
                model="claude-haiku-4-5",
                max_tokens=100,
                stream=True,
            )
            list(result)

        spans = store.get_spans(store.list_traces()[0].trace_id)
        meta = spans[0].metadata
        assert meta is not None
        assert meta["gen_ai.usage.input_tokens"] == 10
        assert meta["gen_ai.usage.output_tokens"] == 5
        assert meta["gen_ai.streaming"] is True

    def test_streaming_no_usage_leaves_tokens_none(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        events = _make_stream_events(["Hi"], input_tokens=None, output_tokens=None)
        fake_stream = MagicMock()
        fake_stream.__iter__ = MagicMock(return_value=iter(events))
        with patch.object(_ant.Messages, "create", return_value=fake_stream):
            _ant_module.instrument()
            result = _ant.Messages.create(
                MagicMock(),
                messages=[],
                model="claude-haiku-4-5",
                max_tokens=100,
                stream=True,
            )
            list(result)

        spans = store.get_spans(store.list_traces()[0].trace_id)
        meta = spans[0].metadata
        assert meta is not None
        assert meta["gen_ai.usage.input_tokens"] is None
        assert meta["gen_ai.usage.output_tokens"] is None

    def test_streaming_yields_events_transparently(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        events = _make_stream_events(["a", "b"])
        fake_stream = MagicMock()
        fake_stream.__iter__ = MagicMock(return_value=iter(events))
        with patch.object(_ant.Messages, "create", return_value=fake_stream):
            _ant_module.instrument()
            result = _ant.Messages.create(
                MagicMock(),
                messages=[],
                model="claude-haiku-4-5",
                max_tokens=100,
                stream=True,
            )
            received = list(result)

        assert received == events

    def test_streaming_error_mid_stream_records_error(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        def _failing_iter() -> Any:
            event = MagicMock()
            event.type = "content_block_delta"
            event.delta.text = "partial"
            yield event
            raise RuntimeError("connection lost")

        fake_stream = MagicMock()
        fake_stream.__iter__ = MagicMock(side_effect=lambda: _failing_iter())
        with patch.object(_ant.Messages, "create", return_value=fake_stream):
            _ant_module.instrument()
            result = _ant.Messages.create(
                MagicMock(),
                messages=[],
                model="claude-haiku-4-5",
                max_tokens=100,
                stream=True,
            )
            with pytest.raises(RuntimeError, match="connection lost"):
                list(result)

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].status == SpanStatus.ERROR
        assert spans[0].error is not None
        assert spans[0].error.message == "connection lost"

    def test_non_streaming_still_works(self, store: TraceStore, patch_global_tracer: None) -> None:
        """Regression: non-streaming path must remain functional."""
        fake = _make_fake_response()
        with patch.object(_ant.Messages, "create", return_value=fake):
            _ant_module.instrument()
            _ant.Messages.create(MagicMock(), messages=[], model="claude-haiku-4-5", max_tokens=100)

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].kind == SpanKind.LLM_CALL
        assert spans[0].outputs is not None
        assert spans[0].outputs["content"] == "Test response"


# ---------------------------------------------------------------------------
# TestAsyncStreaming
# ---------------------------------------------------------------------------


class TestAsyncStreaming:
    async def test_async_streaming_creates_span(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        events = _make_stream_events(["Hello", " async"])

        async def _async_iter() -> Any:
            for e in events:
                yield e

        fake_stream = MagicMock()
        fake_stream.__aiter__ = MagicMock(return_value=_async_iter())
        with patch.object(_ant.AsyncMessages, "create", new=AsyncMock(return_value=fake_stream)):
            _ant_module.instrument()
            result = await _ant.AsyncMessages.create(
                MagicMock(),
                messages=[],
                model="claude-haiku-4-5",
                max_tokens=100,
                stream=True,
            )
            async for _ in result:
                pass

        await asyncio.sleep(0.05)
        traces = store.list_traces()
        assert len(traces) == 1
        spans = store.get_spans(traces[0].trace_id)
        assert len(spans) == 1
        assert spans[0].kind == SpanKind.LLM_CALL

    async def test_async_streaming_captures_content(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        events = _make_stream_events(["foo", "bar"])

        async def _async_iter() -> Any:
            for e in events:
                yield e

        fake_stream = MagicMock()
        fake_stream.__aiter__ = MagicMock(return_value=_async_iter())
        with patch.object(_ant.AsyncMessages, "create", new=AsyncMock(return_value=fake_stream)):
            _ant_module.instrument()
            result = await _ant.AsyncMessages.create(
                MagicMock(),
                messages=[],
                model="claude-haiku-4-5",
                max_tokens=100,
                stream=True,
            )
            async for _ in result:
                pass

        await asyncio.sleep(0.05)
        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].outputs is not None
        assert spans[0].outputs["content"] == "foobar"

    async def test_async_streaming_error_records_error(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        async def _failing_iter() -> Any:
            event = MagicMock()
            event.type = "content_block_delta"
            event.delta.text = "partial"
            yield event
            raise RuntimeError("async connection lost")

        fake_stream = MagicMock()
        fake_stream.__aiter__ = MagicMock(return_value=_failing_iter())
        with patch.object(_ant.AsyncMessages, "create", new=AsyncMock(return_value=fake_stream)):
            _ant_module.instrument()
            result = await _ant.AsyncMessages.create(
                MagicMock(),
                messages=[],
                model="claude-haiku-4-5",
                max_tokens=100,
                stream=True,
            )
            with pytest.raises(RuntimeError, match="async connection lost"):
                async for _ in result:
                    pass

        await asyncio.sleep(0.05)
        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].status == SpanStatus.ERROR
        assert spans[0].error is not None
        assert spans[0].error.message == "async connection lost"
