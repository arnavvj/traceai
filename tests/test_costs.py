"""Tests for traceai.costs — token cost lookup with caching."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import traceai.costs as _costs_module
from traceai.costs import get_cost_usd

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LIVE_PRICES: dict = {
    "gpt-4o": {
        "input_cost_per_token": 2.50e-6,
        "output_cost_per_token": 10.00e-6,
    },
    "gpt-4o-mini": {
        "input_cost_per_token": 0.15e-6,
        "output_cost_per_token": 0.60e-6,
    },
    "_fetched_at": time.time(),
}


# ---------------------------------------------------------------------------
# TestGetCostUsd — live-data path via monkeypatched _get_prices
# ---------------------------------------------------------------------------


class TestGetCostUsd:
    @pytest.fixture(autouse=True)
    def patch_prices(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_costs_module, "_get_prices", lambda: _LIVE_PRICES)

    def test_known_model_returns_correct_float(self) -> None:
        cost = get_cost_usd("gpt-4o", input_tokens=100, output_tokens=50)
        expected = 2.50e-6 * 100 + 10.00e-6 * 50
        assert cost == pytest.approx(expected)

    def test_unknown_model_returns_none(self) -> None:
        assert get_cost_usd("not-a-real-model", input_tokens=100, output_tokens=50) is None

    def test_empty_model_string_returns_none(self) -> None:
        assert get_cost_usd("", input_tokens=10, output_tokens=10) is None

    def test_zero_tokens_known_model_returns_zero_float(self) -> None:
        cost = get_cost_usd("gpt-4o", input_tokens=0, output_tokens=0)
        assert cost == 0.0
        assert cost is not None

    def test_return_type_float_for_known(self) -> None:
        cost = get_cost_usd("gpt-4o-mini", input_tokens=10, output_tokens=5)
        assert isinstance(cost, float)

    def test_return_type_none_for_unknown(self) -> None:
        cost = get_cost_usd("unknown-model-xyz", input_tokens=10, output_tokens=5)
        assert cost is None


# ---------------------------------------------------------------------------
# TestFallback — _get_prices returns {} → must use fallback_prices.json
# ---------------------------------------------------------------------------


class TestFallback:
    @pytest.fixture(autouse=True)
    def patch_prices_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_costs_module, "_get_prices", lambda: {})

    def test_fallback_used_when_live_empty(self) -> None:
        # gpt-4o is in fallback_prices.json — 2.5e-6 in / 1.0e-5 out
        cost = get_cost_usd("gpt-4o", input_tokens=1000, output_tokens=500)
        assert cost == pytest.approx(2.5e-6 * 1000 + 1.0e-5 * 500)

    def test_fallback_gpt4o_mini_correct_price(self) -> None:
        # gpt-4o-mini: 1.5e-7 in / 6.0e-7 out
        cost = get_cost_usd("gpt-4o-mini", input_tokens=200, output_tokens=100)
        assert cost == pytest.approx(1.5e-7 * 200 + 6.0e-7 * 100)

    def test_fallback_claude_sonnet_correct_price(self) -> None:
        # claude-sonnet-4-6: 3.0e-6 in / 1.5e-5 out
        cost = get_cost_usd("claude-sonnet-4-6", input_tokens=500, output_tokens=200)
        assert cost == pytest.approx(3.0e-6 * 500 + 1.5e-5 * 200)

    def test_fallback_unknown_model_returns_none(self) -> None:
        assert get_cost_usd("not-in-fallback-either", input_tokens=100, output_tokens=50) is None


# ---------------------------------------------------------------------------
# TestFallbackPricesFile — sanity checks on the bundled JSON config
# ---------------------------------------------------------------------------


class TestFallbackPricesFile:
    def test_file_is_valid_json(self) -> None:
        data = json.loads(_costs_module._FALLBACK_PRICES_PATH.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_contains_common_models(self) -> None:
        data = json.loads(_costs_module._FALLBACK_PRICES_PATH.read_text(encoding="utf-8"))
        for model in ("gpt-4o", "gpt-4o-mini", "claude-sonnet-4-6", "gemini-1.5-pro"):
            assert model in data, f"Expected {model!r} in fallback_prices.json"

    def test_each_model_has_required_price_fields(self) -> None:
        data = json.loads(_costs_module._FALLBACK_PRICES_PATH.read_text(encoding="utf-8"))
        for key, value in data.items():
            if key.startswith("_"):
                continue  # skip metadata keys
            assert "input_cost_per_token" in value, f"{key} missing input_cost_per_token"
            assert "output_cost_per_token" in value, f"{key} missing output_cost_per_token"
            assert isinstance(value["input_cost_per_token"], float), f"{key} input price not float"
            assert isinstance(value["output_cost_per_token"], float), (
                f"{key} output price not float"
            )

    def test_prices_are_positive(self) -> None:
        data = json.loads(_costs_module._FALLBACK_PRICES_PATH.read_text(encoding="utf-8"))
        for key, value in data.items():
            if key.startswith("_"):
                continue
            assert value["input_cost_per_token"] > 0, f"{key} input price must be > 0"
            assert value["output_cost_per_token"] > 0, f"{key} output price must be > 0"


# ---------------------------------------------------------------------------
# TestCacheLogic — exercises _load_cache, _fetch_and_cache, _get_prices
# ---------------------------------------------------------------------------


class TestCacheLogic:
    def _write_cache(self, path: Path, fetched_at: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "gpt-4o": {"input_cost_per_token": 1.0e-6, "output_cost_per_token": 2.0e-6},
            "_fetched_at": fetched_at,
        }
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_cache_returned_when_fresh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fresh cache (< 24h old) is returned without calling _fetch_and_cache."""
        cache_file = tmp_path / "prices.json"
        self._write_cache(cache_file, fetched_at=time.time())
        monkeypatch.setattr(_costs_module, "_CACHE_PATH", cache_file)

        fetch_called: list[int] = []

        def fake_fetch() -> None:
            fetch_called.append(1)

        monkeypatch.setattr(_costs_module, "_fetch_and_cache", fake_fetch)

        result = _costs_module._get_prices()
        assert "gpt-4o" in result
        assert fetch_called == []  # fetch must NOT have been called

    def test_cache_expired_triggers_refetch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Expired cache (> 24h old) causes _fetch_and_cache to be called."""
        cache_file = tmp_path / "prices.json"
        old_ts = time.time() - 25 * 60 * 60  # 25 hours ago
        self._write_cache(cache_file, fetched_at=old_ts)
        monkeypatch.setattr(_costs_module, "_CACHE_PATH", cache_file)

        fresh_data = {"refreshed": True, "_fetched_at": time.time()}
        monkeypatch.setattr(_costs_module, "_fetch_and_cache", lambda: fresh_data)

        result = _costs_module._get_prices()
        assert result.get("refreshed") is True

    def test_missing_cache_triggers_fetch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When no cache file exists, _fetch_and_cache is called."""
        cache_file = tmp_path / "nonexistent" / "prices.json"
        monkeypatch.setattr(_costs_module, "_CACHE_PATH", cache_file)

        fetched_data = {"fetched": True, "_fetched_at": time.time()}
        monkeypatch.setattr(_costs_module, "_fetch_and_cache", lambda: fetched_data)

        result = _costs_module._get_prices()
        assert result.get("fetched") is True

    def test_fetch_failure_uses_stale_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If fetch fails and cache is expired, stale cache is used as fallback."""
        cache_file = tmp_path / "prices.json"
        old_ts = time.time() - 25 * 60 * 60  # expired
        self._write_cache(cache_file, fetched_at=old_ts)
        monkeypatch.setattr(_costs_module, "_CACHE_PATH", cache_file)
        monkeypatch.setattr(_costs_module, "_fetch_and_cache", lambda: None)  # fetch fails

        result = _costs_module._get_prices()
        # Stale cache should be returned even though expired
        assert "gpt-4o" in result

    def test_fetch_failure_no_cache_uses_fallback_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If fetch fails and no cache, _get_prices returns {} and fallback_prices.json is used."""
        cache_file = tmp_path / "nonexistent" / "prices.json"
        monkeypatch.setattr(_costs_module, "_CACHE_PATH", cache_file)
        monkeypatch.setattr(_costs_module, "_fetch_and_cache", lambda: None)  # fetch fails

        result = _costs_module._get_prices()
        assert result == {}

        # get_cost_usd should fall back to fallback_prices.json for known models
        with patch.object(_costs_module, "_get_prices", return_value={}):
            cost = get_cost_usd("gpt-4o-mini", input_tokens=100, output_tokens=50)
        # Prices from fallback_prices.json: 1.5e-7 in / 6.0e-7 out
        assert cost == pytest.approx(1.5e-7 * 100 + 6.0e-7 * 50)
