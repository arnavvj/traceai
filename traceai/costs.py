"""
Token cost lookup for LLM calls.

Pricing is sourced from LiteLLM's community-maintained JSON (24h TTL cache).

Priority order for _get_prices():
  1. Fresh cache at ~/.traceai/prices.json (< 24h old)
  2. Live fetch from LiteLLM GitHub → updates cache on success
  3. Stale cache (expired but present) — preferred over bundled fallback when offline
  4. Bundled traceai/fallback_prices.json (last resort — edit that file, not this one)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_PRICES_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)
_CACHE_PATH = Path.home() / ".traceai" / "prices.json"
_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours

# Path to the bundled fallback prices config — edit that file to add/update models.
_FALLBACK_PRICES_PATH = Path(__file__).parent / "fallback_prices.json"


def _load_cache(*, ignore_ttl: bool = False) -> dict[str, Any] | None:
    """
    Load cached pricing data from disk.

    Args:
        ignore_ttl: If True, return data even if the cache is expired (stale).
                    Used as a last resort when a fresh fetch has already failed.

    Returns:
        Parsed JSON dict, or None if the file is missing, unreadable, or expired.
    """
    if not _CACHE_PATH.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        if not ignore_ttl:
            fetched_at = data.get("_fetched_at", 0.0)
            if time.time() - float(fetched_at) > _CACHE_TTL_SECONDS:
                return None  # expired — caller will attempt a fresh fetch
        return data
    except Exception:
        return None


def _fetch_and_cache() -> dict[str, Any] | None:
    """
    Fetch the LiteLLM pricing JSON and write it to the local cache.

    Returns:
        Parsed JSON dict on success, or None if the fetch fails for any reason.
        Failures are silent — cost tracking is best-effort and must never break tracing.
    """
    try:
        import httpx

        resp = httpx.get(_PRICES_URL, timeout=5.0, follow_redirects=True)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        data["_fetched_at"] = time.time()
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")
        return data
    except Exception:
        return None  # silent failure — caller tries stale cache, then bundled fallback


def _load_fallback_prices() -> dict[str, Any]:
    """
    Load the bundled fallback prices from traceai/fallback_prices.json.

    Returns an empty dict on any read/parse error so cost tracking degrades
    gracefully rather than crashing.
    """
    try:
        return json.loads(_FALLBACK_PRICES_PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except Exception:
        return {}


def _get_prices() -> dict[str, Any]:
    """
    Return pricing data using the following priority:

    1. Fresh cache (< 24h old)
    2. Live fetch from LiteLLM → updates cache on success
    3. Stale cache (expired but present) — better than bundled fallback when offline
    4. Empty dict — get_cost_usd() then falls through to _load_fallback_prices()
    """
    # 1. Fresh cache
    data = _load_cache(ignore_ttl=False)
    if data is not None:
        return data

    # 2. Live fetch
    data = _fetch_and_cache()
    if data is not None:
        return data

    # 3. Stale cache — more accurate than bundled fallback even if expired
    data = _load_cache(ignore_ttl=True)
    if data is not None:
        return data

    # 4. Signal to caller to use bundled fallback prices
    return {}


def _lookup_entry(
    prices: dict[str, Any], model: str, input_tokens: int, output_tokens: int
) -> float | None:
    """Extract cost from a LiteLLM-format prices dict for a given model, or None."""
    entry = prices.get(model)
    if not isinstance(entry, dict):
        return None
    input_price = entry.get("input_cost_per_token")
    output_price = entry.get("output_cost_per_token")
    if isinstance(input_price, float) and isinstance(output_price, float):
        return input_price * input_tokens + output_price * output_tokens
    return None


def get_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """
    Return the total cost in USD for one LLM call, or None if the model is unknown.

    Pricing is sourced from LiteLLM's community-maintained JSON (24h TTL cache at
    ~/.traceai/prices.json). Falls back to the bundled traceai/fallback_prices.json
    if offline or if the fetch fails. Update fallback_prices.json to add new models
    without modifying Python code.

    Args:
        model:         The model name string (value of gen_ai.request.model metadata key).
        input_tokens:  Number of prompt/input tokens consumed.
        output_tokens: Number of completion/output tokens generated.

    Returns:
        Cost in USD as a float (may be 0.0 for zero tokens on a known model),
        or None if the model is not in any pricing source.
    """
    # Both live/cached data and the bundled fallback use the same LiteLLM format,
    # so the same lookup helper handles both paths.
    cost = _lookup_entry(_get_prices(), model, input_tokens, output_tokens)
    if cost is not None:
        return cost

    return _lookup_entry(_load_fallback_prices(), model, input_tokens, output_tokens)
