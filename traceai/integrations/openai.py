"""
OpenAI auto-instrumentation — Phase 4 implementation.

Patches openai.resources.chat.completions.Completions.create and
AsyncCompletions.create to automatically capture LLM spans.

Captures: model, messages (input), response content, token usage.
Idempotent: calling instrument() multiple times will not double-wrap.
"""

from __future__ import annotations

import functools
from typing import Any

_patched = False


def instrument() -> None:
    """Patch the OpenAI client. Safe to call multiple times."""
    global _patched
    if _patched:
        return
    _patched = True

    import openai.resources.chat.completions as _oai

    import traceai as _traceai
    from traceai.models import SpanKind

    _orig_sync = _oai.Completions.create
    _orig_async = _oai.AsyncCompletions.create

    @functools.wraps(_orig_sync)
    def _sync_wrapper(self: Any, **kwargs: Any) -> Any:
        # Materialize messages to a list — prevents exhausting a one-shot iterable
        # and lets us both log it and pass it to the SDK unchanged.
        messages: list[Any] = list(kwargs.get("messages") or [])
        model: str = str(kwargs.get("model") or "")
        kwargs["messages"] = messages

        with _traceai.tracer.span("openai.chat.completions.create", kind=SpanKind.LLM_CALL) as span:
            span.set_input({"messages": messages, "model": model})
            try:
                response = _orig_sync(self, **kwargs)
            except BaseException as exc:
                span.record_error(exc)
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

            span.set_output({"content": content, "finish_reason": finish_reason})
            span.set_metadata(
                {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": model,
                    "gen_ai.usage.input_tokens": input_tokens,
                    "gen_ai.usage.output_tokens": output_tokens,
                }
            )

        return response

    @functools.wraps(_orig_async)
    async def _async_wrapper(self: Any, **kwargs: Any) -> Any:
        # AsyncCompletions.create is wrapped by @required_args, so
        # inspect.iscoroutinefunction() returns False — but the underlying
        # method is async and must be awaited.
        messages: list[Any] = list(kwargs.get("messages") or [])
        model: str = str(kwargs.get("model") or "")
        kwargs["messages"] = messages

        async with _traceai.tracer.span(
            "openai.chat.completions.create", kind=SpanKind.LLM_CALL
        ) as span:
            span.set_input({"messages": messages, "model": model})
            try:
                response = await _orig_async(self, **kwargs)
            except BaseException as exc:
                span.record_error(exc)
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

            span.set_output({"content": content, "finish_reason": finish_reason})
            span.set_metadata(
                {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": model,
                    "gen_ai.usage.input_tokens": input_tokens,
                    "gen_ai.usage.output_tokens": output_tokens,
                }
            )

        return response

    _oai.Completions.create = _sync_wrapper  # type: ignore[method-assign]
    _oai.AsyncCompletions.create = _async_wrapper  # type: ignore[method-assign]
