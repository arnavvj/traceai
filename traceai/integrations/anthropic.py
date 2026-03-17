"""
Anthropic auto-instrumentation — Phase 4 (v0.2) implementation.

Patches anthropic.resources.messages.Messages.create and
AsyncMessages.create to automatically capture LLM spans.
"""

from __future__ import annotations

_patched = False


def instrument() -> None:
    """Patch the Anthropic client. Safe to call multiple times."""
    # v0.2 implementation
    global _patched
    if _patched:
        return
    _patched = True
    # TODO: wrap anthropic.resources.messages.Messages.create
    # TODO: wrap anthropic.resources.messages.AsyncMessages.create
