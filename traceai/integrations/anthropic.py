"""
Anthropic auto-instrumentation — v0.2 implementation.

Patches anthropic.resources.messages.Messages.create and
AsyncMessages.create to automatically capture LLM spans.

Captures: model, messages (input), response content, token usage.
Idempotent: calling instrument() multiple times will not double-wrap.
"""

from __future__ import annotations

import functools
from typing import Any

_patched = False


def instrument() -> None:
    """Patch the Anthropic client. Safe to call multiple times."""
    global _patched
    if _patched:
        return
    _patched = True

    import anthropic.resources.messages as _ant

    import traceai as _traceai
    from traceai.models import SpanKind

    _orig_sync = _ant.Messages.create
    _orig_async = _ant.AsyncMessages.create

    @functools.wraps(_orig_sync)
    def _sync_wrapper(self: Any, **kwargs: Any) -> Any:
        messages: list[Any] = list(kwargs.get("messages") or [])
        model: str = str(kwargs.get("model") or "")
        kwargs["messages"] = messages

        with _traceai.tracer.span("anthropic.messages.create", kind=SpanKind.LLM_CALL) as span:
            span.set_input({"messages": messages, "model": model})
            try:
                response = _orig_sync(self, **kwargs)
            except BaseException as exc:
                span.record_error(exc)
                raise

            content: str | None = None
            if response.content:
                first = response.content[0]
                content = getattr(first, "text", None)

            stop_reason: str | None = response.stop_reason

            input_tokens: int | None = None
            output_tokens: int | None = None
            if response.usage is not None:
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens

            span.set_output({"content": content, "stop_reason": stop_reason})
            span.set_metadata(
                {
                    "gen_ai.system": "anthropic",
                    "gen_ai.request.model": model,
                    "gen_ai.usage.input_tokens": input_tokens,
                    "gen_ai.usage.output_tokens": output_tokens,
                }
            )

        return response

    @functools.wraps(_orig_async)
    async def _async_wrapper(self: Any, **kwargs: Any) -> Any:
        messages: list[Any] = list(kwargs.get("messages") or [])
        model: str = str(kwargs.get("model") or "")
        kwargs["messages"] = messages

        async with _traceai.tracer.span(
            "anthropic.messages.create", kind=SpanKind.LLM_CALL
        ) as span:
            span.set_input({"messages": messages, "model": model})
            try:
                response = await _orig_async(self, **kwargs)
            except BaseException as exc:
                span.record_error(exc)
                raise

            content = None
            if response.content:
                first = response.content[0]
                content = getattr(first, "text", None)

            stop_reason = response.stop_reason

            input_tokens = None
            output_tokens = None
            if response.usage is not None:
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens

            span.set_output({"content": content, "stop_reason": stop_reason})
            span.set_metadata(
                {
                    "gen_ai.system": "anthropic",
                    "gen_ai.request.model": model,
                    "gen_ai.usage.input_tokens": input_tokens,
                    "gen_ai.usage.output_tokens": output_tokens,
                }
            )

        return response

    _ant.Messages.create = _sync_wrapper  # type: ignore[method-assign]
    _ant.AsyncMessages.create = _async_wrapper  # type: ignore[method-assign]
