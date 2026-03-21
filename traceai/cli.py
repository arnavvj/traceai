"""
TraceAI CLI — Phase 3 implementation.

Commands:
    traceai list      — list recent traces
    traceai inspect   — show span tree for a trace
    traceai export    — export trace as JSON
    traceai open      — launch local dashboard (Phase 5)
    traceai delete    — delete a trace
    traceai config    — manage configuration
"""

from __future__ import annotations

import json
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Annotated

import tomli_w
import typer
from rich import box
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from traceai.models import SpanKind, SpanStatus
from traceai.storage import _DEFAULT_DB_PATH, TraceStore

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# On Windows with a legacy cp1252 terminal, emoji chars are unencodable.
# Detect this and fall back to plain ASCII icons.
_USE_EMOJI = sys.stdout.encoding is not None and sys.stdout.encoding.lower() in (
    "utf-8",
    "utf-16",
    "utf-32",
)

SPAN_KIND_ICONS: dict[str, str]
if _USE_EMOJI:
    SPAN_KIND_ICONS = {
        SpanKind.LLM_CALL: "🤖",
        SpanKind.TOOL_CALL: "🔧",
        SpanKind.MEMORY_READ: "📖",
        SpanKind.MEMORY_WRITE: "✏",
        SpanKind.AGENT_STEP: "~",
        SpanKind.RETRIEVAL: "?",
        SpanKind.EMBEDDING: "#",
        SpanKind.CUSTOM: "*",
    }
else:
    SPAN_KIND_ICONS = {
        SpanKind.LLM_CALL: "[llm]",
        SpanKind.TOOL_CALL: "[tool]",
        SpanKind.MEMORY_READ: "[mem-r]",
        SpanKind.MEMORY_WRITE: "[mem-w]",
        SpanKind.AGENT_STEP: "[agent]",
        SpanKind.RETRIEVAL: "[retr]",
        SpanKind.EMBEDDING: "[embed]",
        SpanKind.CUSTOM: "[*]",
    }

console = Console()
err_console = Console(stderr=True)

CONFIG_PATH = Path.home() / ".traceai" / "config.toml"

STATUS_STYLES: dict[str, str] = {
    "ok": "green",
    "error": "red",
    "pending": "yellow",
    "timeout": "dark_orange",
}

VALID_STATUSES = {"ok", "error", "pending", "timeout"}

# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="traceai",
    help="Chrome DevTools for AI agents.",
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_store(db: Path | None) -> TraceStore:
    try:
        return TraceStore(db_path=db)
    except Exception as e:
        err_console.print(f"[red]Cannot open database: {e}[/red]")
        raise typer.Exit(1)


def _resolve_trace_id(store: TraceStore, prefix: str) -> str:
    """Resolve a short prefix to a full trace_id.

    Queries up to 500 traces — sufficient for v0.1 local use.
    """
    traces = store.list_traces(limit=500)
    matches = [t for t in traces if t.trace_id.startswith(prefix)]
    if not matches:
        err_console.print(f"[red]No trace found matching prefix: {prefix}[/red]")
        raise typer.Exit(1)
    if len(matches) > 1:
        err_console.print(
            f"[red]Ambiguous prefix '{prefix}' — {len(matches)} traces match. "
            "Use more characters.[/red]"
        )
        raise typer.Exit(1)
    return matches[0].trace_id


def _status_style(status: str) -> str:
    return STATUS_STYLES.get(status, "white")


def _fmt_duration(ms: float | None) -> str:
    if ms is None:
        return "-"
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.2f}s"


def _fmt_datetime(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _read_config() -> dict[str, object]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        err_console.print("[yellow]Warning: config file is malformed — using defaults.[/yellow]")
        return {}


def _write_config(data: dict[str, object]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(tomli_w.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("list")
def list_traces(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max traces to show")] = 20,
    status: Annotated[
        str | None, typer.Option("--status", help="Filter by status: ok|error|pending|timeout")
    ] = None,
    db: Annotated[Path | None, typer.Option("--db", help="Path to SQLite database")] = None,
) -> None:
    """List recent agent traces."""
    if status is not None and status not in VALID_STATUSES:
        err_console.print(
            f"[red]Invalid status '{status}'. Must be one of: ok, error, pending, timeout[/red]"
        )
        raise typer.Exit(1)

    store = _get_store(db)
    traces = store.list_traces(limit=limit, status=status)

    if not traces:
        console.print("[dim]No traces found. Run an agent to generate traces.[/dim]")
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("ID", style="dim", no_wrap=True, min_width=8)
    table.add_column("Name", min_width=12)
    table.add_column("Status", no_wrap=True)
    table.add_column("Spans", justify="right")
    table.add_column("LLM Calls", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Started", style="dim")

    for t in traces:
        style = _status_style(t.status.value)
        table.add_row(
            t.trace_id[:8],
            t.name,
            f"[{style}]{t.status.value}[/{style}]",
            str(t.span_count),
            str(t.llm_call_count),
            _fmt_duration(t.duration_ms),
            _fmt_datetime(t.started_at),
        )

    console.print(table)


@app.command("inspect")
def inspect_trace(
    trace_id: Annotated[str, typer.Argument(help="Trace ID or 8-char prefix")],
    full: Annotated[bool, typer.Option("--full", help="Show inputs/outputs/metadata")] = False,
    db: Annotated[Path | None, typer.Option("--db", help="Path to SQLite database")] = None,
) -> None:
    """Show the full span tree for a trace."""
    store = _get_store(db)
    full_id = _resolve_trace_id(store, trace_id)
    trace = store.get_trace(full_id)
    if trace is None:
        err_console.print(f"[red]Trace not found: {full_id}[/red]")
        raise typer.Exit(1)
    spans = store.get_spans(full_id)

    style = _status_style(trace.status.value)
    header = (
        f"[bold]{trace.name}[/bold]  "
        f"[dim]{full_id[:8]}[/dim]  "
        f"[{style}]{trace.status.value}[/{style}]  "
        f"{_fmt_duration(trace.duration_ms)}  "
        f"[dim]{_fmt_datetime(trace.started_at)}[/dim]"
    )
    tree = Tree(header)

    # Two-pass tree construction: build node map, then attach children
    nodes: dict[str, Tree] = {}
    for span in spans:
        icon = SPAN_KIND_ICONS.get(span.kind, "•")
        span_style = _status_style(span.status.value)
        label = (
            f"{icon} [bold]{span.name}[/bold]  "
            f"[dim]{span.kind.value}[/dim]  "
            f"{_fmt_duration(span.duration_ms)}  "
            f"[{span_style}]{span.status.value}[/{span_style}]"
        )
        if span.status == SpanStatus.ERROR and span.error:
            label += f"\n  [red]{span.error.exception_type}: {span.error.message}[/red]"
        if full:
            for field_name, value in [
                ("inputs", span.inputs),
                ("outputs", span.outputs),
                ("metadata", span.metadata),
            ]:
                if value is not None:
                    label += f"\n  [dim]{field_name}:[/dim] {json.dumps(value, default=str)}"
        nodes[span.span_id] = Tree(label)

    for span in spans:
        node = nodes[span.span_id]
        if span.parent_span_id and span.parent_span_id in nodes:
            nodes[span.parent_span_id].add(node)
        else:
            tree.add(node)

    console.print(tree)


@app.command("export")
def export_trace(
    trace_id: Annotated[str, typer.Argument(help="Trace ID or 8-char prefix")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Output file path (default: stdout)")
    ] = None,
    db: Annotated[Path | None, typer.Option("--db", help="Path to SQLite database")] = None,
) -> None:
    """Export a trace and all its spans as JSON."""
    store = _get_store(db)
    full_id = _resolve_trace_id(store, trace_id)
    trace = store.get_trace(full_id)
    if trace is None:
        err_console.print(f"[red]Trace not found: {full_id}[/red]")
        raise typer.Exit(1)
    spans = store.get_spans(full_id)

    data = {
        "trace": trace.model_dump(mode="json"),
        "spans": [s.model_dump(mode="json") for s in spans],
    }
    json_str = json.dumps(data, indent=2, default=str)

    if output is None:
        print(json_str)
    else:
        output.write_text(json_str, encoding="utf-8")
        err_console.print(f"[green]Exported to {output}[/green]")


@app.command("delete")
def delete_trace(
    trace_id: Annotated[str, typer.Argument(help="Trace ID or 8-char prefix")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt")] = False,
    db: Annotated[Path | None, typer.Option("--db", help="Path to SQLite database")] = None,
) -> None:
    """Delete a trace and all its spans."""
    store = _get_store(db)
    full_id = _resolve_trace_id(store, trace_id)

    if not yes:
        typer.confirm(f"Delete trace {full_id[:8]}...?", abort=True)

    store.delete_trace(full_id)
    console.print(f"[green]Deleted trace {full_id[:8]}[/green]")


@app.command("open")
def open_dashboard(
    port: Annotated[int, typer.Option("--port", "-p", help="Port to listen on")] = 8765,
    host: Annotated[str, typer.Option("--host", help="Host to bind")] = "127.0.0.1",
    no_browser: Annotated[
        bool, typer.Option("--no-browser", help="Don't open browser automatically")
    ] = False,
    db: Annotated[Path | None, typer.Option("--db", help="Path to SQLite database")] = None,
) -> None:
    """Launch the TraceAI web dashboard."""
    import threading
    import webbrowser

    from traceai.server import run_server

    store = _get_store(db)
    url = f"http://{host}:{port}"
    console.print(f"[bold]TraceAI dashboard[/bold] → [cyan]{url}[/cyan]")
    console.print("Press [bold]Ctrl+C[/bold] to stop.\n")

    if not no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    try:
        run_server(db_path=store.db_path, host=host, port=port)
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped.[/yellow]")


@app.command("config")
def config(
    set_db: Annotated[
        Path | None, typer.Option("--set-db", help="Set default database path")
    ] = None,
) -> None:
    """Show or update TraceAI configuration."""
    if set_db is not None:
        data = _read_config()
        data["db_path"] = str(set_db.expanduser().resolve())
        _write_config(data)
        console.print(f"[green]Default database set to {data['db_path']}[/green]")

    cfg = _read_config()
    effective_db = str(cfg.get("db_path", str(_DEFAULT_DB_PATH)))

    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("DB Path", effective_db)
    table.add_row("Config File", str(CONFIG_PATH))
    table.add_row("Version", "0.1.0")
    console.print(table)
