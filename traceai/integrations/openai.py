"""
OpenAI auto-instrumentation — Phase 4 implementation.

Patches openai.resources.chat.completions.Completions.create and
AsyncCompletions.create to automatically capture LLM spans.

Captures: model, messages (input), response content, token usage.
Idempotent: calling instrument() multiple times will not double-wrap.
"""

from __future__ import annotations

_patched = False


def instrument() -> None:
    """Patch the OpenAI client. Safe to call multiple times."""
    # Phase 4 implementation
    global _patched
    if _patched:
        return
    _patched = True
    # TODO: wrap openai.resources.chat.completions.Completions.create
    # TODO: wrap openai.resources.chat.completions.AsyncCompletions.create
