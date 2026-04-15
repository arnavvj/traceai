"""Tests for traceai.integrations.openai — OpenAI auto-instrumentation patch."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import openai.resources.chat.completions as _oai
import pytest

import traceai
import traceai.integrations.openai as _oai_module
from traceai.models import SpanKind, SpanStatus
from traceai.storage import TraceStore
from traceai.tracer import Tracer, _current_span_id, _current_trace_id

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_response(
    content: str = "Test response",
    finish_reason: str = "stop",
    model: str = "gpt-4o",
    prompt_tokens: int = 42,
    completion_tokens: int = 128,
) -> MagicMock:
    """Build a realistic fake ChatCompletion MagicMock."""
    response = MagicMock()
    response.model = model
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = finish_reason
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
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
    original_sync = _oai.Completions.create
    original_async = _oai.AsyncCompletions.create
    monkeypatch.setattr(_oai_module, "_patched", False)
    yield  # type: ignore[misc]
    _oai.Completions.create = original_sync  # type: ignore[method-assign]
    _oai.AsyncCompletions.create = original_async  # type: ignore[method-assign]
    _oai_module._patched = False
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
        original = _oai.Completions.create
        _oai_module.instrument()
        assert _oai.Completions.create is not original

    def test_instrument_twice_does_not_double_wrap(self) -> None:
        _oai_module.instrument()
        patched_once = _oai.Completions.create
        _oai_module.instrument()  # second call — must be a no-op
        assert _oai.Completions.create is patched_once


# ---------------------------------------------------------------------------
# TestSyncPatch
# ---------------------------------------------------------------------------


class TestSyncPatch:
    def test_span_created_with_correct_kind(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        fake = _make_fake_response()
        with patch.object(_oai.Completions, "create", return_value=fake):
            _oai_module.instrument()
            _oai.Completions.create(MagicMock(), messages=[], model="gpt-4o")

        traces = store.list_traces()
        assert len(traces) == 1
        spans = store.get_spans(traces[0].trace_id)
        assert len(spans) == 1
        assert spans[0].kind == SpanKind.LLM_CALL

    def test_span_captures_inputs(self, store: TraceStore, patch_global_tracer: None) -> None:
        fake = _make_fake_response()
        messages = [{"role": "user", "content": "Hello"}]
        with patch.object(_oai.Completions, "create", return_value=fake):
            _oai_module.instrument()
            _oai.Completions.create(MagicMock(), messages=messages, model="gpt-4o")

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].inputs == {"messages": messages, "model": "gpt-4o"}

    def test_span_captures_outputs(self, store: TraceStore, patch_global_tracer: None) -> None:
        fake = _make_fake_response(content="Paris", finish_reason="stop")
        with patch.object(_oai.Completions, "create", return_value=fake):
            _oai_module.instrument()
            _oai.Completions.create(MagicMock(), messages=[], model="gpt-4o")

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].outputs == {"content": "Paris", "finish_reason": "stop"}

    def test_span_captures_token_metadata(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        fake = _make_fake_response(prompt_tokens=10, completion_tokens=20)
        with patch.object(_oai.Completions, "create", return_value=fake):
            _oai_module.instrument()
            _oai.Completions.create(MagicMock(), messages=[], model="gpt-4o-mini")

        spans = store.get_spans(store.list_traces()[0].trace_id)
        meta = spans[0].metadata
        assert meta is not None
        assert meta["gen_ai.system"] == "openai"
        assert meta["gen_ai.request.model"] == "gpt-4o-mini"
        assert meta["gen_ai.usage.input_tokens"] == 10
        assert meta["gen_ai.usage.output_tokens"] == 20

    def test_span_error_on_exception(self, store: TraceStore, patch_global_tracer: None) -> None:
        with patch.object(_oai.Completions, "create", side_effect=RuntimeError("API error")):
            _oai_module.instrument()
            with pytest.raises(RuntimeError, match="API error"):
                _oai.Completions.create(MagicMock(), messages=[], model="gpt-4o")

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
        with patch.object(_oai.Completions, "create", return_value=fake):
            _oai_module.instrument()
            # No @tracer.trace wrapping — implicit trace should be auto-created
            _oai.Completions.create(MagicMock(), messages=[], model="gpt-4o")

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
        with patch.object(_oai.AsyncCompletions, "create", new=AsyncMock(return_value=fake)):
            _oai_module.instrument()
            await _oai.AsyncCompletions.create(
                MagicMock(),
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o",
            )

        # Give the event loop enough cycles for fire-and-forget save tasks to complete.
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
            _oai.AsyncCompletions,
            "create",
            new=AsyncMock(side_effect=RuntimeError("async API error")),
        ):
            _oai_module.instrument()
            with pytest.raises(RuntimeError, match="async API error"):
                await _oai.AsyncCompletions.create(MagicMock(), messages=[], model="gpt-4o")

        await asyncio.sleep(0.05)
        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].status == SpanStatus.ERROR
        assert spans[0].error is not None
        assert spans[0].error.message == "async API error"


# ---------------------------------------------------------------------------
# Streaming helpers
# ---------------------------------------------------------------------------


def _make_stream_chunks(
    content_parts: list[str],
    finish_reason: str = "stop",
    prompt_tokens: int | None = 42,
    completion_tokens: int | None = 128,
) -> list[MagicMock]:
    """Build a list of fake ChatCompletionChunk objects for streaming tests."""
    chunks: list[MagicMock] = []
    for part in content_parts:
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = part
        chunk.choices[0].finish_reason = None
        chunk.usage = None
        chunks.append(chunk)
    # Final chunk with finish_reason and optional usage
    final = MagicMock()
    final.choices = [MagicMock()]
    final.choices[0].delta.content = None
    final.choices[0].finish_reason = finish_reason
    if prompt_tokens is not None and completion_tokens is not None:
        final.usage.prompt_tokens = prompt_tokens
        final.usage.completion_tokens = completion_tokens
    else:
        final.usage = None
    chunks.append(final)
    return chunks


# ---------------------------------------------------------------------------
# TestSyncStreaming
# ---------------------------------------------------------------------------


class TestSyncStreaming:
    def test_streaming_creates_span_with_correct_kind(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        chunks = _make_stream_chunks(["Hello", " world"])
        fake_stream = MagicMock()
        fake_stream.__iter__ = MagicMock(return_value=iter(chunks))
        with patch.object(_oai.Completions, "create", return_value=fake_stream):
            _oai_module.instrument()
            result = _oai.Completions.create(MagicMock(), messages=[], model="gpt-4o", stream=True)
            list(result)  # consume

        traces = store.list_traces()
        assert len(traces) == 1
        spans = store.get_spans(traces[0].trace_id)
        assert len(spans) == 1
        assert spans[0].kind == SpanKind.LLM_CALL

    def test_streaming_captures_accumulated_content(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        chunks = _make_stream_chunks(["Hello", " ", "world"])
        fake_stream = MagicMock()
        fake_stream.__iter__ = MagicMock(return_value=iter(chunks))
        with patch.object(_oai.Completions, "create", return_value=fake_stream):
            _oai_module.instrument()
            result = _oai.Completions.create(MagicMock(), messages=[], model="gpt-4o", stream=True)
            list(result)

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].outputs is not None
        assert spans[0].outputs["content"] == "Hello world"
        assert spans[0].outputs["finish_reason"] == "stop"

    def test_streaming_captures_token_usage(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        chunks = _make_stream_chunks(["Hi"], prompt_tokens=10, completion_tokens=5)
        fake_stream = MagicMock()
        fake_stream.__iter__ = MagicMock(return_value=iter(chunks))
        with patch.object(_oai.Completions, "create", return_value=fake_stream):
            _oai_module.instrument()
            result = _oai.Completions.create(MagicMock(), messages=[], model="gpt-4o", stream=True)
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
        chunks = _make_stream_chunks(["Hi"], prompt_tokens=None, completion_tokens=None)
        fake_stream = MagicMock()
        fake_stream.__iter__ = MagicMock(return_value=iter(chunks))
        with patch.object(_oai.Completions, "create", return_value=fake_stream):
            _oai_module.instrument()
            result = _oai.Completions.create(MagicMock(), messages=[], model="gpt-4o", stream=True)
            list(result)

        spans = store.get_spans(store.list_traces()[0].trace_id)
        meta = spans[0].metadata
        assert meta is not None
        assert meta["gen_ai.usage.input_tokens"] is None
        assert meta["gen_ai.usage.output_tokens"] is None

    def test_streaming_yields_chunks_transparently(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        chunks = _make_stream_chunks(["a", "b"])
        fake_stream = MagicMock()
        fake_stream.__iter__ = MagicMock(return_value=iter(chunks))
        with patch.object(_oai.Completions, "create", return_value=fake_stream):
            _oai_module.instrument()
            result = _oai.Completions.create(MagicMock(), messages=[], model="gpt-4o", stream=True)
            received = list(result)

        assert received == chunks

    def test_streaming_error_mid_stream_records_error(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        def _failing_iter() -> Any:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = "partial"
            chunk.choices[0].finish_reason = None
            chunk.usage = None
            yield chunk
            raise RuntimeError("connection lost")

        fake_stream = MagicMock()
        fake_stream.__iter__ = MagicMock(side_effect=lambda: _failing_iter())
        with patch.object(_oai.Completions, "create", return_value=fake_stream):
            _oai_module.instrument()
            result = _oai.Completions.create(MagicMock(), messages=[], model="gpt-4o", stream=True)
            with pytest.raises(RuntimeError, match="connection lost"):
                list(result)

        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].status == SpanStatus.ERROR
        assert spans[0].error is not None
        assert spans[0].error.message == "connection lost"

    def test_non_streaming_still_works(self, store: TraceStore, patch_global_tracer: None) -> None:
        """Regression: non-streaming path must remain functional."""
        fake = _make_fake_response()
        with patch.object(_oai.Completions, "create", return_value=fake):
            _oai_module.instrument()
            _oai.Completions.create(MagicMock(), messages=[], model="gpt-4o")

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
        chunks = _make_stream_chunks(["Hello", " async"])

        async def _async_iter() -> Any:
            for c in chunks:
                yield c

        fake_stream = MagicMock()
        fake_stream.__aiter__ = MagicMock(return_value=_async_iter())
        with patch.object(_oai.AsyncCompletions, "create", new=AsyncMock(return_value=fake_stream)):
            _oai_module.instrument()
            result = await _oai.AsyncCompletions.create(
                MagicMock(), messages=[], model="gpt-4o", stream=True
            )
            collected = []
            async for c in result:
                collected.append(c)

        await asyncio.sleep(0.05)
        traces = store.list_traces()
        assert len(traces) == 1
        spans = store.get_spans(traces[0].trace_id)
        assert len(spans) == 1
        assert spans[0].kind == SpanKind.LLM_CALL

    async def test_async_streaming_captures_content(
        self, store: TraceStore, patch_global_tracer: None
    ) -> None:
        chunks = _make_stream_chunks(["foo", "bar"])

        async def _async_iter() -> Any:
            for c in chunks:
                yield c

        fake_stream = MagicMock()
        fake_stream.__aiter__ = MagicMock(return_value=_async_iter())
        with patch.object(_oai.AsyncCompletions, "create", new=AsyncMock(return_value=fake_stream)):
            _oai_module.instrument()
            result = await _oai.AsyncCompletions.create(
                MagicMock(), messages=[], model="gpt-4o", stream=True
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
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = "partial"
            chunk.choices[0].finish_reason = None
            chunk.usage = None
            yield chunk
            raise RuntimeError("async connection lost")

        fake_stream = MagicMock()
        fake_stream.__aiter__ = MagicMock(return_value=_failing_iter())
        with patch.object(_oai.AsyncCompletions, "create", new=AsyncMock(return_value=fake_stream)):
            _oai_module.instrument()
            result = await _oai.AsyncCompletions.create(
                MagicMock(), messages=[], model="gpt-4o", stream=True
            )
            with pytest.raises(RuntimeError, match="async connection lost"):
                async for _ in result:
                    pass

        await asyncio.sleep(0.05)
        spans = store.get_spans(store.list_traces()[0].trace_id)
        assert spans[0].status == SpanStatus.ERROR
        assert spans[0].error is not None
        assert spans[0].error.message == "async connection lost"
