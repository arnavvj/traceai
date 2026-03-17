"""
TraceAI CLI — Phase 3 implementation.

Commands:
    traceai list      — list recent traces
    traceai inspect   — show span tree for a trace
    traceai export    — export trace as JSON
    traceai open      — launch local dashboard
    traceai delete    — delete a trace
    traceai config    — manage configuration
"""

import typer

app = typer.Typer(
    name="traceai",
    help="Chrome DevTools for AI agents.",
    no_args_is_help=True,
)

# Phase 3 implementation
