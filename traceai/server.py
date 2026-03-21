from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from traceai.models import Span, SpanStatus, Trace
from traceai.storage import TraceStore

_DASHBOARD_HTML = Path(__file__).parent / "dashboard" / "index.html"

_store: TraceStore | None = None


def get_store() -> TraceStore:
    if _store is None:
        raise HTTPException(status_code=503, detail="Store not initialized")
    return _store


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class TracesResponse(BaseModel):
    traces: list[Trace]
    limit: int
    offset: int


class TraceResponse(BaseModel):
    trace: Trace


class SpansResponse(BaseModel):
    spans: list[Span]


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(db_path: Path | None = None) -> FastAPI:
    global _store
    _store = TraceStore(db_path=db_path)

    app = FastAPI(title="TraceAI", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _valid_statuses = {s.value for s in SpanStatus}

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(_DASHBOARD_HTML)

    # ------------------------------------------------------------------
    # Traces
    # ------------------------------------------------------------------

    @app.get("/api/traces", response_model=TracesResponse)
    async def list_traces(
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        status: Annotated[str | None, Query()] = None,
        store: TraceStore = Depends(get_store),
    ) -> TracesResponse:
        if status is not None and status not in _valid_statuses:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. Must be one of: {sorted(_valid_statuses)}",
            )
        traces = await store.alist_traces(limit=limit, offset=offset, status=status)
        return TracesResponse(traces=traces, limit=limit, offset=offset)

    @app.get("/api/traces/{trace_id}", response_model=TraceResponse)
    async def get_trace(
        trace_id: str,
        store: TraceStore = Depends(get_store),
    ) -> TraceResponse:
        trace = await store.aget_trace(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="Trace not found")
        return TraceResponse(trace=trace)

    @app.get("/api/traces/{trace_id}/spans", response_model=SpansResponse)
    async def get_spans(
        trace_id: str,
        store: TraceStore = Depends(get_store),
    ) -> SpansResponse:
        spans = await store.aget_spans(trace_id)
        return SpansResponse(spans=spans)

    return app


# ---------------------------------------------------------------------------
# Server entrypoint
# ---------------------------------------------------------------------------


def run_server(
    db_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    import uvicorn

    app = create_app(db_path=db_path)
    uvicorn.run(app, host=host, port=port)
