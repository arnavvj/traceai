"""
OpenAI auto-instrumentation.

Patches openai.resources.chat.completions.Completions.create and
AsyncCompletions.create to automatically capture LLM spans.

Captures: model, messages (input), response content, token usage.
Handles both streaming (``stream=True``) and non-streaming calls.
Idempotent: calling instrument() multiple times will not double-wrap.
"""

from __future__ import annotations

import functools
from contextvars import Token
from typing import Any

from traceai.models import Span, SpanKind
from traceai.tracer import SpanContext, _run_async, _tracing_suppressed

_patched = False


# ---------------------------------------------------------------------------
# Stream wrappers — proxy the OpenAI Stream/AsyncStream objects, buffering
# content and token usage, then closing the span when the stream is consumed.
# ---------------------------------------------------------------------------


class _SyncStreamWrapper:
    """Wraps an OpenAI sync ``Stream`` to capture content and finalize the span."""

    def __init__(
        self,
        stream: Any,
        span_ctx: SpanContext,
        span: Span,
        tok_trace: Token[str | None],
        tok_span: Token[str | None],
        tracer: Any,
        model: str,
        temperature: Any = None,
        max_tokens: Any = None,
    ) -> None:
        self._stream = stream
        self._iter = iter(stream)
        self._span_ctx = span_ctx
        self._span = span
        self._tok_trace = tok_trace
        self._tok_span = tok_span
        self._tracer = tracer
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._content_parts: list[str] = []
        self._finish_reason: str | None = None
        self._input_tokens: int | None = None
        self._output_tokens: int | None = None
        self._closed = False

    def __iter__(self) -> _SyncStreamWrapper:
        return self

    def __next__(self) -> Any:
        try:
            chunk = next(self._iter)
        except StopIteration:
            self._finalize()
            raise
        except BaseException as exc:
            self._finalize(exc)
            raise
        self._process_chunk(chunk)
        return chunk

    def __enter__(self) -> _SyncStreamWrapper:
        return self

    def __exit__(self, *args: Any) -> None:
        self._finalize()
        if hasattr(self._stream, "__exit__"):
            self._stream.__exit__(*args)

    def close(self) -> None:
        self._finalize()
        if hasattr(self._stream, "close"):
            self._stream.close()

    def _process_chunk(self, chunk: Any) -> None:
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta and getattr(delta, "content", None):
                self._content_parts.append(delta.content)
            fr = chunk.choices[0].finish_reason
            if fr is not None:
                self._finish_reason = fr
        if getattr(chunk, "usage", None) is not None:
            self._input_tokens = chunk.usage.prompt_tokens
            self._output_tokens = chunk.usage.completion_tokens

    def _finalize(self, exc: BaseException | None = None) -> None:
        if self._closed:
            return
        self._closed = True
        content = "".join(self._content_parts) if self._content_parts else None
        self._span_ctx.set_output({"content": content, "finish_reason": self._finish_reason})
        _meta: dict[str, Any] = {
            "gen_ai.system": "openai",
            "gen_ai.request.model": self._model,
            "gen_ai.usage.input_tokens": self._input_tokens,
            "gen_ai.usage.output_tokens": self._output_tokens,
            "gen_ai.response.finish_reason": self._finish_reason,
            "gen_ai.streaming": True,
        }
        if self._temperature is not None:
            _meta["gen_ai.request.temperature"] = self._temperature
        if self._max_tokens is not None:
            _meta["gen_ai.request.max_tokens"] = self._max_tokens
        self._span_ctx.set_metadata(_meta)
        if exc is not None:
            self._span_ctx.record_error(exc)
        self._tracer._close_span(self._span, self._tok_trace, self._tok_span, exc)
        _run_async(self._tracer._save_span_async(self._span))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


class _AsyncStreamWrapper:
    """Wraps an OpenAI async ``AsyncStream`` to capture content and finalize the span."""

    def __init__(
        self,
        stream: Any,
        span_ctx: SpanContext,
        span: Span,
        tok_trace: Token[str | None],
        tok_span: Token[str | None],
        tracer: Any,
        model: str,
        temperature: Any = None,
        max_tokens: Any = None,
    ) -> None:
        self._stream = stream
        self._aiter = stream.__aiter__()
        self._span_ctx = span_ctx
        self._span = span
        self._tok_trace = tok_trace
        self._tok_span = tok_span
        self._tracer = tracer
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._content_parts: list[str] = []
        self._finish_reason: str | None = None
        self._input_tokens: int | None = None
        self._output_tokens: int | None = None
        self._closed = False

    def __aiter__(self) -> _AsyncStreamWrapper:
        return self

    async def __anext__(self) -> Any:
        try:
            chunk = await self._aiter.__anext__()
        except StopAsyncIteration:
            await self._finalize()
            raise
        except BaseException as exc:
            await self._finalize(exc)
            raise
        self._process_chunk(chunk)
        return chunk

    async def __aenter__(self) -> _AsyncStreamWrapper:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._finalize()
        if hasattr(self._stream, "__aexit__"):
            await self._stream.__aexit__(*args)

    async def close(self) -> None:
        await self._finalize()
        if hasattr(self._stream, "close"):
            result = self._stream.close()
            if hasattr(result, "__await__"):
                await result

    def _process_chunk(self, chunk: Any) -> None:
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta and getattr(delta, "content", None):
                self._content_parts.append(delta.content)
            fr = chunk.choices[0].finish_reason
            if fr is not None:
                self._finish_reason = fr
        if getattr(chunk, "usage", None) is not None:
            self._input_tokens = chunk.usage.prompt_tokens
            self._output_tokens = chunk.usage.completion_tokens

    async def _finalize(self, exc: BaseException | None = None) -> None:
        if self._closed:
            return
        self._closed = True
        content = "".join(self._content_parts) if self._content_parts else None
        self._span_ctx.set_output({"content": content, "finish_reason": self._finish_reason})
        _meta: dict[str, Any] = {
            "gen_ai.system": "openai",
            "gen_ai.request.model": self._model,
            "gen_ai.usage.input_tokens": self._input_tokens,
            "gen_ai.usage.output_tokens": self._output_tokens,
            "gen_ai.response.finish_reason": self._finish_reason,
            "gen_ai.streaming": True,
        }
        if self._temperature is not None:
            _meta["gen_ai.request.temperature"] = self._temperature
        if self._max_tokens is not None:
            _meta["gen_ai.request.max_tokens"] = self._max_tokens
        self._span_ctx.set_metadata(_meta)
        if exc is not None:
            self._span_ctx.record_error(exc)
        self._tracer._close_span(self._span, self._tok_trace, self._tok_span, exc)
        await self._tracer._save_span_async(self._span)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


# ---------------------------------------------------------------------------
# Instrument entry point
# ---------------------------------------------------------------------------


def instrument() -> None:
    """Patch the OpenAI client. Safe to call multiple times."""
    global _patched
    if _patched:
        return
    _patched = True

    import openai.resources.chat.completions as _oai

    import traceai as _traceai

    _orig_sync = _oai.Completions.create
    _orig_async = _oai.AsyncCompletions.create

    @functools.wraps(_orig_sync)
    def _sync_wrapper(self: Any, **kwargs: Any) -> Any:
        if _tracing_suppressed.get():
            return _orig_sync(self, **kwargs)
        messages: list[Any] = list(kwargs.get("messages") or [])
        model: str = str(kwargs.get("model") or "")
        temperature = kwargs.get("temperature")
        max_tokens = kwargs.get("max_tokens")
        kwargs["messages"] = messages
        is_stream = bool(kwargs.get("stream"))

        if is_stream:
            span, tok_trace, tok_span = _traceai.tracer._make_span(
                "openai.chat.completions.create", SpanKind.LLM_CALL, None
            )
            span_ctx = SpanContext(span, _traceai.tracer._store)
            span_ctx.set_input({"messages": messages, "model": model})
            try:
                stream = _orig_sync(self, **kwargs)
            except BaseException as exc:
                span_ctx.record_error(exc)
                _traceai.tracer._close_span(span, tok_trace, tok_span, exc)
                _run_async(_traceai.tracer._save_span_async(span))
                raise
            return _SyncStreamWrapper(
                stream,
                span_ctx,
                span,
                tok_trace,
                tok_span,
                _traceai.tracer,
                model,
                temperature,
                max_tokens,
            )

        with _traceai.tracer.span(
            "openai.chat.completions.create", kind=SpanKind.LLM_CALL
        ) as span_ctx:
            span_ctx.set_input({"messages": messages, "model": model})
            try:
                response = _orig_sync(self, **kwargs)
            except BaseException as exc:
                span_ctx.record_error(exc)
                raise

            content: str | None = None
            finish_reason: str | None = None
            if response.choices:
                first = response.choices[0]
                content = first.message.content if first.message else None
                finish_reason = first.finish_reason

            input_tokens: int | None = None
            output_tokens: int | None = None
            if response.usage is not None:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens

            span_ctx.set_output({"content": content, "finish_reason": finish_reason})
            _meta: dict[str, Any] = {
                "gen_ai.system": "openai",
                "gen_ai.request.model": model,
                "gen_ai.usage.input_tokens": input_tokens,
                "gen_ai.usage.output_tokens": output_tokens,
                "gen_ai.response.finish_reason": finish_reason,
            }
            if temperature is not None:
                _meta["gen_ai.request.temperature"] = temperature
            if max_tokens is not None:
                _meta["gen_ai.request.max_tokens"] = max_tokens
            span_ctx.set_metadata(_meta)

        return response

    @functools.wraps(_orig_async)
    async def _async_wrapper(self: Any, **kwargs: Any) -> Any:
        if _tracing_suppressed.get():
            return await _orig_async(self, **kwargs)
        messages: list[Any] = list(kwargs.get("messages") or [])
        model: str = str(kwargs.get("model") or "")
        temperature = kwargs.get("temperature")
        max_tokens = kwargs.get("max_tokens")
        kwargs["messages"] = messages
        is_stream = bool(kwargs.get("stream"))

        if is_stream:
            span, tok_trace, tok_span = _traceai.tracer._make_span(
                "openai.chat.completions.create", SpanKind.LLM_CALL, None
            )
            span_ctx = SpanContext(span, _traceai.tracer._store)
            span_ctx.set_input({"messages": messages, "model": model})
            try:
                stream = await _orig_async(self, **kwargs)
            except BaseException as exc:
                span_ctx.record_error(exc)
                _traceai.tracer._close_span(span, tok_trace, tok_span, exc)
                await _traceai.tracer._save_span_async(span)
                raise
            return _AsyncStreamWrapper(
                stream,
                span_ctx,
                span,
                tok_trace,
                tok_span,
                _traceai.tracer,
                model,
                temperature,
                max_tokens,
            )

        async with _traceai.tracer.span(
            "openai.chat.completions.create", kind=SpanKind.LLM_CALL
        ) as span_ctx:
            span_ctx.set_input({"messages": messages, "model": model})
            try:
                response = await _orig_async(self, **kwargs)
            except BaseException as exc:
                span_ctx.record_error(exc)
                raise

            content = None
            finish_reason = None
            if response.choices:
                first = response.choices[0]
                content = first.message.content if first.message else None
                finish_reason = first.finish_reason

            input_tokens = None
            output_tokens = None
            if response.usage is not None:
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens

            span_ctx.set_output({"content": content, "finish_reason": finish_reason})
            _meta2: dict[str, Any] = {
                "gen_ai.system": "openai",
                "gen_ai.request.model": model,
                "gen_ai.usage.input_tokens": input_tokens,
                "gen_ai.usage.output_tokens": output_tokens,
                "gen_ai.response.finish_reason": finish_reason,
            }
            if temperature is not None:
                _meta2["gen_ai.request.temperature"] = temperature
            if max_tokens is not None:
                _meta2["gen_ai.request.max_tokens"] = max_tokens
            span_ctx.set_metadata(_meta2)

        return response

    _oai.Completions.create = _sync_wrapper  # type: ignore[method-assign]
    _oai.AsyncCompletions.create = _async_wrapper  # type: ignore[method-assign]
