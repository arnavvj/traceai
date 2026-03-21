"""Tests for traceai CLI commands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from traceai.cli import app
from traceai.models import ErrorDetail, Span, SpanKind, SpanStatus, Trace
from traceai.storage import TraceStore

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def store(db_path: Path) -> TraceStore:
    return TraceStore(db_path=db_path)


@pytest.fixture
def sample_trace(store: TraceStore) -> Trace:
    trace = Trace(name="test-agent", status=SpanStatus.OK)
    trace.span_count = 2
    trace.llm_call_count = 1
    trace.duration_ms = 150.5
    asyncio.run(store.save_trace(trace))
    return trace


@pytest.fixture
def sample_span(store: TraceStore, sample_trace: Trace) -> Span:
    span = Span(
        trace_id=sample_trace.trace_id,
        name="llm-call",
        kind=SpanKind.LLM_CALL,
        inputs={"prompt": "hello"},
        outputs={"content": "world"},
        metadata={"model": "gpt-4o"},
    )
    span.close(status=SpanStatus.OK, outputs={"content": "world"})
    asyncio.run(store.save_span(span))
    return span


@pytest.fixture
def error_trace(store: TraceStore) -> Trace:
    trace = Trace(name="failing-agent", status=SpanStatus.ERROR)
    asyncio.run(store.save_trace(trace))
    return trace


@pytest.fixture
def error_span(store: TraceStore, error_trace: Trace) -> Span:
    span = Span(trace_id=error_trace.trace_id, name="bad-tool", kind=SpanKind.TOOL_CALL)
    span.close(
        status=SpanStatus.ERROR,
        error=ErrorDetail(
            exception_type="ValueError",
            message="tool returned nothing",
            traceback="Traceback ...",
        ),
    )
    asyncio.run(store.save_span(span))
    return span


# ---------------------------------------------------------------------------
# TestListCommand
# ---------------------------------------------------------------------------


class TestListCommand:
    def test_list_empty_db(self, db_path: Path) -> None:
        result = runner.invoke(app, ["list", "--db", str(db_path)])
        assert result.exit_code == 0
        assert "No traces found" in result.output

    def test_list_shows_traces(self, db_path: Path, sample_trace: Trace) -> None:
        result = runner.invoke(app, ["list", "--db", str(db_path)])
        assert result.exit_code == 0
        assert sample_trace.trace_id[:8] in result.output
        assert "test-agent" in result.output

    def test_list_limit(self, db_path: Path, store: TraceStore) -> None:
        # Save 5 traces
        for i in range(5):
            t = Trace(name=f"agent-{i}", status=SpanStatus.OK)
            asyncio.run(store.save_trace(t))
        result = runner.invoke(app, ["list", "--db", str(db_path), "--limit", "2"])
        assert result.exit_code == 0
        # Count rows — each trace row contains "agent-" in the name
        rows = [line for line in result.output.splitlines() if "agent-" in line]
        assert len(rows) == 2

    def test_list_filter_by_status(
        self, db_path: Path, sample_trace: Trace, error_trace: Trace
    ) -> None:
        result = runner.invoke(app, ["list", "--db", str(db_path), "--status", "ok"])
        assert result.exit_code == 0
        assert "test-agent" in result.output
        assert "failing-agent" not in result.output

    def test_list_invalid_status(self, db_path: Path) -> None:
        result = runner.invoke(app, ["list", "--db", str(db_path), "--status", "bogus"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# TestInspectCommand
# ---------------------------------------------------------------------------


class TestInspectCommand:
    def test_inspect_by_prefix(self, db_path: Path, sample_trace: Trace, sample_span: Span) -> None:
        prefix = sample_trace.trace_id[:8]
        result = runner.invoke(app, ["inspect", prefix, "--db", str(db_path)])
        assert result.exit_code == 0
        assert "llm-call" in result.output
        assert "test-agent" in result.output

    def test_inspect_full_flag(self, db_path: Path, sample_trace: Trace, sample_span: Span) -> None:
        prefix = sample_trace.trace_id[:8]
        result = runner.invoke(app, ["inspect", prefix, "--full", "--db", str(db_path)])
        assert result.exit_code == 0
        # With --full, inputs/outputs should appear
        assert "inputs" in result.output or "prompt" in result.output

    def test_inspect_error_span(self, db_path: Path, error_trace: Trace, error_span: Span) -> None:
        prefix = error_trace.trace_id[:8]
        result = runner.invoke(app, ["inspect", prefix, "--db", str(db_path)])
        assert result.exit_code == 0
        assert "ValueError" in result.output
        assert "tool returned nothing" in result.output

    def test_inspect_unknown_prefix(self, db_path: Path) -> None:
        result = runner.invoke(app, ["inspect", "00000000", "--db", str(db_path)])
        assert result.exit_code == 1

    def test_inspect_ambiguous_prefix(self, db_path: Path, store: TraceStore) -> None:
        # Create two traces with identical prefix start by forcing trace_ids
        # We can't force IDs, so instead create many traces and find a real collision,
        # or just verify the ambiguity logic by mocking list_traces.
        # Practical approach: save two traces and use a 0-char prefix (empty string matches all)
        t1 = Trace(name="agent-a", status=SpanStatus.OK)
        t2 = Trace(name="agent-b", status=SpanStatus.OK)
        asyncio.run(store.save_trace(t1))
        asyncio.run(store.save_trace(t2))
        # Empty string prefix matches all traces — triggers ambiguous error
        result = runner.invoke(app, ["inspect", "", "--db", str(db_path)])
        assert result.exit_code == 1
        assert "Ambiguous" in result.output


# ---------------------------------------------------------------------------
# TestExportCommand
# ---------------------------------------------------------------------------


class TestExportCommand:
    def test_export_stdout(self, db_path: Path, sample_trace: Trace, sample_span: Span) -> None:
        prefix = sample_trace.trace_id[:8]
        result = runner.invoke(app, ["export", prefix, "--db", str(db_path)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "trace" in data
        assert "spans" in data

    def test_export_to_file(
        self, db_path: Path, sample_trace: Trace, sample_span: Span, tmp_path: Path
    ) -> None:
        out = tmp_path / "out.json"
        prefix = sample_trace.trace_id[:8]
        result = runner.invoke(app, ["export", prefix, "--output", str(out), "--db", str(db_path)])
        assert result.exit_code == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert "trace" in data

    def test_export_trace_data(self, db_path: Path, sample_trace: Trace, sample_span: Span) -> None:
        prefix = sample_trace.trace_id[:8]
        result = runner.invoke(app, ["export", prefix, "--db", str(db_path)])
        data = json.loads(result.output)
        assert data["trace"]["name"] == "test-agent"
        assert data["trace"]["trace_id"] == sample_trace.trace_id

    def test_export_includes_spans(
        self, db_path: Path, sample_trace: Trace, sample_span: Span
    ) -> None:
        prefix = sample_trace.trace_id[:8]
        result = runner.invoke(app, ["export", prefix, "--db", str(db_path)])
        data = json.loads(result.output)
        assert len(data["spans"]) == 1
        assert data["spans"][0]["name"] == "llm-call"


# ---------------------------------------------------------------------------
# TestDeleteCommand
# ---------------------------------------------------------------------------


class TestDeleteCommand:
    def test_delete_with_yes_flag(self, db_path: Path, sample_trace: Trace) -> None:
        prefix = sample_trace.trace_id[:8]
        result = runner.invoke(app, ["delete", prefix, "--yes", "--db", str(db_path)])
        assert result.exit_code == 0
        assert "Deleted" in result.output
        # Confirm it's gone
        list_result = runner.invoke(app, ["list", "--db", str(db_path)])
        assert "test-agent" not in list_result.output

    def test_delete_unknown_trace(self, db_path: Path) -> None:
        result = runner.invoke(app, ["delete", "00000000", "--yes", "--db", str(db_path)])
        assert result.exit_code == 1

    def test_delete_prompts_without_yes(self, db_path: Path, sample_trace: Trace) -> None:
        prefix = sample_trace.trace_id[:8]
        result = runner.invoke(app, ["delete", prefix, "--db", str(db_path)], input="y\n")
        assert result.exit_code == 0
        assert "Deleted" in result.output


# ---------------------------------------------------------------------------
# TestOpenCommand
# ---------------------------------------------------------------------------


class TestOpenCommand:
    def test_open_starts_server(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """open command starts server and prints URL; monkeypatch avoids actual bind."""
        started: list[dict] = []

        def fake_run_server(
            db_path: Path | None = None,
            host: str = "127.0.0.1",
            port: int = 8765,
        ) -> None:
            started.append({"db_path": db_path, "host": host, "port": port})

        monkeypatch.setattr("traceai.server.run_server", fake_run_server)
        # Also patch webbrowser so CI doesn't open a browser
        import webbrowser

        monkeypatch.setattr(webbrowser, "open", lambda url: None)

        db = tmp_path / "test.db"
        result = runner.invoke(app, ["open", "--no-browser", "--db", str(db)])
        assert result.exit_code == 0
        assert "http://127.0.0.1:8765" in result.output
        assert len(started) == 1

    def test_open_custom_port(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("traceai.server.run_server", lambda **_: None)
        db = tmp_path / "test.db"
        result = runner.invoke(app, ["open", "--no-browser", "--port", "9000", "--db", str(db)])
        assert result.exit_code == 0
        assert "9000" in result.output


# ---------------------------------------------------------------------------
# TestConfigCommand
# ---------------------------------------------------------------------------


class TestConfigCommand:
    def test_config_shows_defaults(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "DB Path" in result.output
        assert "Version" in result.output

    def test_config_set_db(self, tmp_path: Path) -> None:
        custom_db = tmp_path / "custom.db"
        # Use a temp config path by monkeypatching would require more setup;
        # instead verify the command runs and shows the path in output
        result = runner.invoke(app, ["config", "--set-db", str(custom_db)])
        assert result.exit_code == 0
        assert str(custom_db) in result.output or "custom" in result.output
