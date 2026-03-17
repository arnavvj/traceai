"""
Core Tracer — async-safe tracing primitives using contextvars.

Usage:
    from traceai import tracer

    @tracer.trace
    def my_agent(prompt: str) -> str:
        with tracer.span("llm-call", kind="llm_call") as span:
            span.set_input({"prompt": prompt})
            result = call_llm(prompt)
            span.set_output({"response": result})
        return result

    # async works identically
    @tracer.trace
    async def my_async_agent(prompt: str) -> str:
        async with tracer.span("llm-call", kind="llm_call") as span:
            span.set_input({"prompt": prompt})
            result = await call_llm_async(prompt)
            span.set_output({"response": result})
        return result
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable
from contextvars import ContextVar, Token
from typing import Any, TypeVar

from traceai.models import ErrorDetail, Span, SpanKind, SpanStatus, Trace
from traceai.storage import TraceStore

F = TypeVar("F", bound=Callable[..., Any])


def _run_async(coro: Any) -> None:
    """Run a coroutine from any context — sync or inside a running event loop."""
    try:
        loop = asyncio.get_running_loop()
        # Already inside an event loop (e.g. async test, Jupyter).
        # Schedule as a fire-and-forget task instead of blocking.
        loop.create_task(coro)
    except RuntimeError:
        # No running loop — safe to use asyncio.run().
        asyncio.run(coro)


# ------------------------------------------------------------------
# Context propagation — ContextVar is async-safe:
# each asyncio.Task gets its own copy automatically, so concurrent
# agent runs never bleed context into each other.
# ------------------------------------------------------------------
_current_trace_id: ContextVar[str | None] = ContextVar("traceai_trace_id", default=None)
_current_span_id: ContextVar[str | None] = ContextVar("traceai_span_id", default=None)


class SpanContext:
    """
    Live handle to an open span. Returned by `with tracer.span(...) as span:`.

    All mutations are applied to the in-memory Span object. The span is
    persisted to the TraceStore when the context manager exits.
    """

    def __init__(self, span: Span, store: TraceStore) -> None:
        self._span = span
        self._store = store

    @property
    def span_id(self) -> str:
        return self._span.span_id

    @property
    def trace_id(self) -> str:
        return self._span.trace_id

    def set_input(self, data: dict[str, Any]) -> None:
        self._span.inputs = data

    def set_output(self, data: dict[str, Any]) -> None:
        self._span.outputs = data

    def set_metadata(self, data: dict[str, Any]) -> None:
        if self._span.metadata is None:
            self._span.metadata = {}
        self._span.metadata.update(data)

    def set_status(self, status: SpanStatus) -> None:
        self._span.status = status

    def record_error(self, exc: BaseException) -> None:
        self._span.error = ErrorDetail.from_exception(exc)
        self._span.status = SpanStatus.ERROR

    def add_tag(self, key: str, value: str) -> None:
        if self._span.metadata is None:
            self._span.metadata = {}
        self._span.metadata[f"tag.{key}"] = value


class Tracer:
    """
    Global tracer. Obtain via the module-level singleton:

        from traceai import tracer
    """

    def __init__(self, store: TraceStore | None = None) -> None:
        self._store = store or TraceStore()

    @property
    def store(self) -> TraceStore:
        return self._store

    # ------------------------------------------------------------------
    # current_* accessors — used by integrations (openai patch, etc.)
    # ------------------------------------------------------------------

    def current_trace_id(self) -> str | None:
        return _current_trace_id.get()

    def current_span_id(self) -> str | None:
        return _current_span_id.get()

    # ------------------------------------------------------------------
    # @tracer.trace decorator
    # ------------------------------------------------------------------

    def trace(
        self,
        func: F | None = None,
        *,
        name: str | None = None,
        tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> F | Callable[[F], F]:
        """
        Decorator that wraps an entire function as a root Trace.

        Can be used with or without arguments:
            @tracer.trace
            def fn(): ...

            @tracer.trace(name="custom-name", tags={"env": "prod"})
            def fn(): ...
        """
        def decorator(fn: F) -> F:
            trace_name = name or fn.__name__

            if inspect.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    return await self._run_trace_async(
                        fn, args, kwargs, trace_name, tags, metadata
                    )
                return async_wrapper  # type: ignore[return-value]
            else:
                @functools.wraps(fn)
                def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    return self._run_trace_sync(
                        fn, args, kwargs, trace_name, tags, metadata
                    )
                return sync_wrapper  # type: ignore[return-value]

        # Called as @tracer.trace (no parentheses) — func is the decorated fn
        if func is not None:
            return decorator(func)
        # Called as @tracer.trace(...) — return the decorator
        return decorator

    def _run_trace_sync(
        self,
        fn: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        name: str,
        tags: dict[str, str] | None,
        metadata: dict[str, Any] | None,
    ) -> Any:
        trace = Trace(name=name, tags=tags or {}, metadata=metadata)

        # Capture root-level inputs as positional/keyword args summary
        try:
            sig = inspect.signature(fn)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            trace.inputs = dict(bound.arguments)
        except Exception:
            pass

        tok_trace = _current_trace_id.set(trace.trace_id)
        tok_span = _current_span_id.set(None)
        try:
            result = fn(*args, **kwargs)
            trace.outputs = {"result": result}
            trace.close(status=SpanStatus.OK)
            return result
        except BaseException:
            trace.close(status=SpanStatus.ERROR)
            raise
        finally:
            _current_trace_id.reset(tok_trace)
            _current_span_id.reset(tok_span)
            _run_async(self._finalize_trace(trace))

    async def _run_trace_async(
        self,
        fn: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        name: str,
        tags: dict[str, str] | None,
        metadata: dict[str, Any] | None,
    ) -> Any:
        trace = Trace(name=name, tags=tags or {}, metadata=metadata)

        try:
            sig = inspect.signature(fn)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            trace.inputs = dict(bound.arguments)
        except Exception:
            pass

        tok_trace = _current_trace_id.set(trace.trace_id)
        tok_span = _current_span_id.set(None)
        try:
            result = await fn(*args, **kwargs)
            trace.outputs = {"result": result}
            trace.close(status=SpanStatus.OK)
            return result
        except BaseException:
            trace.close(status=SpanStatus.ERROR)
            raise
        finally:
            _current_trace_id.reset(tok_trace)
            _current_span_id.reset(tok_span)
            await self._finalize_trace(trace)

    async def _finalize_trace(self, trace: Trace) -> None:
        """Persist trace after updating summary counters from its spans."""
        await self._store.save_trace(trace)

    # ------------------------------------------------------------------
    # tracer.span() context manager
    # ------------------------------------------------------------------

    def span(
        self,
        name: str,
        *,
        kind: SpanKind | str = SpanKind.CUSTOM,
        metadata: dict[str, Any] | None = None,
    ) -> _SyncSpanCM | _AsyncSpanCM:
        """
        Context manager that creates a child span within the current trace.

        Works in both sync and async contexts:

            # sync
            with tracer.span("step") as span:
                span.set_input({"x": 1})

            # async
            async with tracer.span("step") as span:
                span.set_input({"x": 1})

        Returns a dual-mode context manager that supports both `with` and
        `async with` — so the same call works in either context.
        """
        if isinstance(kind, str):
            kind = SpanKind(kind)
        return _DualSpanCM(self, name, kind, metadata)

    def _make_span(
        self,
        name: str,
        kind: SpanKind,
        metadata: dict[str, Any] | None,
    ) -> tuple[Span, Token[str | None], Token[str | None]]:
        trace_id = _current_trace_id.get()
        if trace_id is None:
            # No active trace — create an implicit one so spans always have a home.
            # This is a convenience for quick scripts; proper use wraps with @trace.
            trace = Trace(name=f"implicit-{name}")
            trace_id = trace.trace_id
            # We can't await here; schedule the save on the event loop if running,
            # otherwise fall back to sync. This is best-effort for the implicit case.
            _run_async(self._store.save_trace(trace))
            _current_trace_id.set(trace_id)

        parent_span_id = _current_span_id.get()
        span = Span(
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            name=name,
            kind=kind,
            metadata=metadata,
        )
        tok_span = _current_span_id.set(span.span_id)
        tok_trace = _current_trace_id.set(trace_id)  # re-set to get a reset token
        return span, tok_trace, tok_span

    def _close_span(
        self,
        span: Span,
        tok_trace: Token[str | None],
        tok_span: Token[str | None],
        exc: BaseException | None,
    ) -> None:
        if exc is not None:
            span.close(error=ErrorDetail.from_exception(exc))
        elif span.status == SpanStatus.PENDING:
            # Only default to OK if not already set by span.record_error() etc.
            span.close(status=SpanStatus.OK)
        else:
            # Status was set manually (e.g. via record_error) — just close timing.
            span.close(status=span.status)
        _current_span_id.reset(tok_span)
        _current_trace_id.reset(tok_trace)

    async def _save_span_async(self, span: Span) -> None:
        await self._store.save_span(span)


# ------------------------------------------------------------------
# Dual-mode context manager — supports both `with` and `async with`
# ------------------------------------------------------------------

class _DualSpanCM:
    """
    A context manager object that works as both sync (`with`) and
    async (`async with`). This lets the same `tracer.span()` call
    work in either context without the user needing to know which they're in.
    """

    def __init__(
        self,
        tracer: Tracer,
        name: str,
        kind: SpanKind,
        metadata: dict[str, Any] | None,
    ) -> None:
        self._tracer = tracer
        self._name = name
        self._kind = kind
        self._metadata = metadata
        self._span: Span | None = None
        self._tok_trace: Token[str | None] | None = None
        self._tok_span: Token[str | None] | None = None
        self._ctx: SpanContext | None = None

    # Sync protocol
    def __enter__(self) -> SpanContext:
        span, tok_trace, tok_span = self._tracer._make_span(
            self._name, self._kind, self._metadata
        )
        self._span = span
        self._tok_trace = tok_trace
        self._tok_span = tok_span
        self._ctx = SpanContext(span, self._tracer._store)
        return self._ctx

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        assert self._span and self._tok_trace and self._tok_span
        self._tracer._close_span(
            self._span, self._tok_trace, self._tok_span, exc_val
        )
        # Persist — run async save from sync context
        _run_async(self._tracer._save_span_async(self._span))

    # Async protocol
    async def __aenter__(self) -> SpanContext:
        span, tok_trace, tok_span = self._tracer._make_span(
            self._name, self._kind, self._metadata
        )
        self._span = span
        self._tok_trace = tok_trace
        self._tok_span = tok_span
        self._ctx = SpanContext(span, self._tracer._store)
        return self._ctx

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        assert self._span and self._tok_trace and self._tok_span
        self._tracer._close_span(
            self._span, self._tok_trace, self._tok_span, exc_val
        )
        await self._tracer._save_span_async(self._span)


# Aliases for type annotations
_SyncSpanCM = _DualSpanCM
_AsyncSpanCM = _DualSpanCM
