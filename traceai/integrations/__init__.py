"""
Auto-instrumentation for known LLM provider SDKs.

Usage:
    import traceai
    traceai.instrument("openai")     # patches openai client globally
    traceai.instrument("anthropic")  # patches anthropic client globally
"""

from __future__ import annotations

_SUPPORTED = {"openai", "anthropic"}


def instrument(provider: str) -> None:
    """
    Patch a known LLM provider SDK to auto-capture spans.

    Idempotent — safe to call multiple times.
    """
    provider = provider.lower().strip()
    if provider not in _SUPPORTED:
        raise ValueError(f"Unsupported provider: {provider!r}. Supported: {sorted(_SUPPORTED)}")
    if provider == "openai":
        from traceai.integrations.openai import instrument as _patch

        _patch()
    elif provider == "anthropic":
        from traceai.integrations.anthropic import instrument as _patch  # type: ignore[no-redef]

        _patch()
