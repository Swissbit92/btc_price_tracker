"""Tests for the XS universe selection logic (pure, no network)."""

from __future__ import annotations

import importlib.util
import os

import pytest

_PATH = os.path.join(os.path.dirname(__file__), "..", "tools", "xs", "select_xs_universe.py")
_spec = importlib.util.spec_from_file_location("select_xs_universe", _PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _mkt(swap=True, linear=True, active=True, quote="USDT", settle="USDT"):
    return {"swap": swap, "linear": linear, "active": active, "quote": quote, "settle": settle}


def test_symbol_mapping():
    assert mod.ccxt_to_tracker_symbol("BTC/USDT:USDT") == "BTC-USDT"
    assert mod.ccxt_to_tracker_symbol("PEPE/USDT:USDT") == "PEPE-USDT"


def test_ranks_by_quote_volume_desc_and_limits_top_n():
    markets = {"A/USDT:USDT": _mkt(), "B/USDT:USDT": _mkt(), "C/USDT:USDT": _mkt()}
    tickers = {"A/USDT:USDT": {"quoteVolume": 100},
               "B/USDT:USDT": {"quoteVolume": 300},
               "C/USDT:USDT": {"quoteVolume": 200}}
    out = mod.select_top_perps(markets, tickers, top_n=2)
    assert [r["symbol"] for r in out] == ["B-USDT", "C-USDT"]   # highest volume first, top-2


def test_filters_non_perp_and_non_usdt():
    markets = {
        "SWAP/USDT:USDT": _mkt(),
        "SPOT/USDT:USDT": _mkt(swap=False),        # not a swap
        "INVERSE/USD:USD": _mkt(linear=False, quote="USD", settle="USD"),
        "DELISTED/USDT:USDT": _mkt(active=False),  # inactive
        "COINM/USDT:BTC": _mkt(settle="BTC"),      # not USDT-settled
    }
    tickers = {k: {"quoteVolume": 100} for k in markets}
    out = mod.select_top_perps(markets, tickers, top_n=10)
    assert [r["symbol"] for r in out] == ["SWAP-USDT"]


def test_quote_volume_fallback_from_base_times_last():
    markets = {"X/USDT:USDT": _mkt()}
    tickers = {"X/USDT:USDT": {"baseVolume": 10, "last": 5}}   # no quoteVolume → 10*5
    out = mod.select_top_perps(markets, tickers, top_n=1)
    assert out[0]["quote_volume_24h"] == pytest.approx(50.0)


def test_missing_ticker_ranks_last_not_crash():
    markets = {"A/USDT:USDT": _mkt(), "B/USDT:USDT": _mkt()}
    tickers = {"A/USDT:USDT": {"quoteVolume": 100}}   # B has no ticker → 0.0, ranked last
    out = mod.select_top_perps(markets, tickers, top_n=10)
    assert [r["symbol"] for r in out] == ["A-USDT", "B-USDT"]
    assert out[1]["quote_volume_24h"] == 0.0
