from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from traceai.models import ErrorDetail, Span, SpanKind, SpanStatus, Trace

_DEFAULT_DB_PATH = Path.home() / ".traceai" / "traces.db"

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS traces (
    trace_id        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    duration_ms     REAL,
    span_count      INTEGER NOT NULL DEFAULT 0,
    llm_call_count  INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER,
    total_cost_usd  REAL,
    status          TEXT NOT NULL DEFAULT 'pending',
    tags            TEXT NOT NULL DEFAULT '{}',
    inputs          TEXT,
    outputs         TEXT,
    metadata        TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spans (
    span_id         TEXT PRIMARY KEY,
    trace_id        TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
    parent_span_id  TEXT,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    duration_ms     REAL,
    inputs          TEXT,
    outputs         TEXT,
    metadata        TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    error           TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_spans_trace_id    ON spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_spans_parent      ON spans(parent_span_id);
CREATE INDEX IF NOT EXISTS idx_spans_kind        ON spans(kind);
CREATE INDEX IF NOT EXISTS idx_traces_started_at ON traces(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_traces_status     ON traces(status);
"""


def _dt_to_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _str_to_dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _json_dumps(obj: Any) -> str | None:
    if obj is None:
        return None
    return json.dumps(obj)


def _json_loads(s: str | None) -> Any:
    if s is None:
        return None
    return json.loads(s)


def _trace_to_row(t: Trace) -> dict[str, Any]:
    return {
        "trace_id": t.trace_id,
        "name": t.name,
        "started_at": _dt_to_str(t.started_at),
        "ended_at": _dt_to_str(t.ended_at),
        "duration_ms": t.duration_ms,
        "span_count": t.span_count,
        "llm_call_count": t.llm_call_count,
        "total_tokens": t.total_tokens,
        "total_cost_usd": t.total_cost_usd,
        "status": t.status.value,
        "tags": json.dumps(t.tags),
        "inputs": _json_dumps(t.inputs),
        "outputs": _json_dumps(t.outputs),
        "metadata": _json_dumps(t.metadata),
        "created_at": _dt_to_str(t.created_at),
    }


def _row_to_trace(row: dict[str, Any]) -> Trace:
    return Trace(
        trace_id=row["trace_id"],
        name=row["name"],
        started_at=_str_to_dt(row["started_at"]),  # type: ignore[arg-type]
        ended_at=_str_to_dt(row["ended_at"]),
        duration_ms=row["duration_ms"],
        span_count=row["span_count"],
        llm_call_count=row["llm_call_count"],
        total_tokens=row["total_tokens"],
        total_cost_usd=row["total_cost_usd"],
        status=SpanStatus(row["status"]),
        tags=json.loads(row["tags"]),
        inputs=_json_loads(row["inputs"]),
        outputs=_json_loads(row["outputs"]),
        metadata=_json_loads(row["metadata"]),
        created_at=_str_to_dt(row["created_at"]),  # type: ignore[arg-type]
    )


def _span_to_row(s: Span) -> dict[str, Any]:
    return {
        "span_id": s.span_id,
        "trace_id": s.trace_id,
        "parent_span_id": s.parent_span_id,
        "name": s.name,
        "kind": s.kind.value,
        "started_at": _dt_to_str(s.started_at),
        "ended_at": _dt_to_str(s.ended_at),
        "duration_ms": s.duration_ms,
        "inputs": _json_dumps(s.inputs),
        "outputs": _json_dumps(s.outputs),
        "metadata": _json_dumps(s.metadata),
        "status": s.status.value,
        "error": _json_dumps(s.error.model_dump() if s.error else None),
        "created_at": _dt_to_str(s.created_at),
    }


def _row_to_span(row: dict[str, Any]) -> Span:
    error_data = _json_loads(row["error"])
    return Span(
        span_id=row["span_id"],
        trace_id=row["trace_id"],
        parent_span_id=row["parent_span_id"],
        name=row["name"],
        kind=SpanKind(row["kind"]),
        started_at=_str_to_dt(row["started_at"]),  # type: ignore[arg-type]
        ended_at=_str_to_dt(row["ended_at"]),
        duration_ms=row["duration_ms"],
        inputs=_json_loads(row["inputs"]),
        outputs=_json_loads(row["outputs"]),
        metadata=_json_loads(row["metadata"]),
        status=SpanStatus(row["status"]),
        error=ErrorDetail(**error_data) if error_data else None,
        created_at=_str_to_dt(row["created_at"]),  # type: ignore[arg-type]
    )


class TraceStore:
    """
    Synchronous + asynchronous SQLite-backed store for traces and spans.

    Sync methods are used by the CLI.
    Async methods are used by the tracer and FastAPI server.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema_sync()

    # ------------------------------------------------------------------
    # Schema init (sync, runs once at construction)
    # ------------------------------------------------------------------

    def _init_schema_sync(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)

    @staticmethod
    def _configure_conn(conn: sqlite3.Connection) -> None:
        """Enable foreign keys and WAL mode on every new sync connection."""
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")

    # ------------------------------------------------------------------
    # Async write methods (used by tracer during agent runs)
    # ------------------------------------------------------------------

    async def save_trace(self, trace: Trace) -> None:
        row = _trace_to_row(trace)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO traces
                    (trace_id, name, started_at, ended_at, duration_ms,
                     span_count, llm_call_count, total_tokens, total_cost_usd,
                     status, tags, inputs, outputs, metadata, created_at)
                VALUES
                    (:trace_id, :name, :started_at, :ended_at, :duration_ms,
                     :span_count, :llm_call_count, :total_tokens, :total_cost_usd,
                     :status, :tags, :inputs, :outputs, :metadata, :created_at)
                """,
                row,
            )
            await db.commit()

    async def save_span(self, span: Span) -> None:
        row = _span_to_row(span)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO spans
                    (span_id, trace_id, parent_span_id, name, kind,
                     started_at, ended_at, duration_ms,
                     inputs, outputs, metadata, status, error, created_at)
                VALUES
                    (:span_id, :trace_id, :parent_span_id, :name, :kind,
                     :started_at, :ended_at, :duration_ms,
                     :inputs, :outputs, :metadata, :status, :error, :created_at)
                """,
                row,
            )
            await db.commit()

    # ------------------------------------------------------------------
    # Async read methods (used by FastAPI server)
    # ------------------------------------------------------------------

    async def aget_trace(self, trace_id: str) -> Trace | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM traces WHERE trace_id = ?", (trace_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return _row_to_trace(dict(row))

    async def alist_traces(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[Trace]:
        query = "SELECT * FROM traces"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [_row_to_trace(dict(r)) for r in rows]

    async def aget_spans(self, trace_id: str) -> list[Span]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM spans WHERE trace_id = ? ORDER BY started_at ASC",
                (trace_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [_row_to_span(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # Sync read methods (used by CLI — no event loop required)
    # ------------------------------------------------------------------

    def get_trace(self, trace_id: str) -> Trace | None:
        with sqlite3.connect(self.db_path) as conn:
            self._configure_conn(conn)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM traces WHERE trace_id = ?", (trace_id,)
            ).fetchone()
            if row is None:
                return None
            return _row_to_trace(dict(row))

    def list_traces(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[Trace]:
        query = "SELECT * FROM traces"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with sqlite3.connect(self.db_path) as conn:
            self._configure_conn(conn)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [_row_to_trace(dict(r)) for r in rows]

    def get_spans(self, trace_id: str) -> list[Span]:
        with sqlite3.connect(self.db_path) as conn:
            self._configure_conn(conn)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM spans WHERE trace_id = ? ORDER BY started_at ASC",
                (trace_id,),
            ).fetchall()
            return [_row_to_span(dict(r)) for r in rows]

    def delete_trace(self, trace_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            self._configure_conn(conn)
            cursor = conn.execute(
                "DELETE FROM traces WHERE trace_id = ?", (trace_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
