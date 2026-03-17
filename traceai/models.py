from __future__ import annotations

import traceback as tb
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid4().hex


class SpanKind(StrEnum):
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    AGENT_STEP = "agent_step"
    RETRIEVAL = "retrieval"
    EMBEDDING = "embedding"
    CUSTOM = "custom"


class SpanStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    PENDING = "pending"


class ErrorDetail(BaseModel):
    exception_type: str
    message: str
    traceback: str | None = None

    @classmethod
    def from_exception(cls, exc: BaseException) -> ErrorDetail:
        return cls(
            exception_type=type(exc).__qualname__,
            message=str(exc),
            traceback="".join(tb.format_exception(type(exc), exc, exc.__traceback__)),
        )


class Span(BaseModel):
    # Identity
    span_id: str = Field(default_factory=_new_id)
    trace_id: str
    parent_span_id: str | None = None

    # Classification
    name: str
    kind: SpanKind = SpanKind.CUSTOM

    # Timing
    started_at: datetime = Field(default_factory=_now)
    ended_at: datetime | None = None
    duration_ms: float | None = None  # stored redundantly for query perf

    # Payload — JSON blobs, schema varies per kind
    inputs: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None
    # Aligned with OTel GenAI Semantic Conventions where applicable:
    # gen_ai.system, gen_ai.request.model, gen_ai.usage.input_tokens, etc.
    metadata: dict[str, Any] | None = None

    # Status
    status: SpanStatus = SpanStatus.PENDING
    error: ErrorDetail | None = None

    created_at: datetime = Field(default_factory=_now)

    def close(
        self,
        *,
        status: SpanStatus = SpanStatus.OK,
        outputs: dict[str, Any] | None = None,
        error: ErrorDetail | None = None,
    ) -> None:
        self.ended_at = _now()
        self.duration_ms = (self.ended_at - self.started_at).total_seconds() * 1000
        self.status = status
        if outputs is not None:
            self.outputs = outputs
        if error is not None:
            self.error = error
            self.status = SpanStatus.ERROR


class Trace(BaseModel):
    # Identity
    trace_id: str = Field(default_factory=_new_id)
    name: str

    # Timing
    started_at: datetime = Field(default_factory=_now)
    ended_at: datetime | None = None
    duration_ms: float | None = None

    # Summary — denormalized for list-view performance
    span_count: int = 0
    llm_call_count: int = 0
    total_tokens: int | None = None
    total_cost_usd: float | None = None

    # Status — reflects worst child span status
    status: SpanStatus = SpanStatus.PENDING

    # Free-form tagging for filtering: {"env": "prod", "agent": "research"}
    tags: dict[str, str] = Field(default_factory=dict)

    # Root-level agent inputs/outputs
    inputs: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    created_at: datetime = Field(default_factory=_now)

    def close(
        self,
        *,
        status: SpanStatus = SpanStatus.OK,
        outputs: dict[str, Any] | None = None,
    ) -> None:
        self.ended_at = _now()
        self.duration_ms = (self.ended_at - self.started_at).total_seconds() * 1000
        self.status = status
        if outputs is not None:
            self.outputs = outputs
