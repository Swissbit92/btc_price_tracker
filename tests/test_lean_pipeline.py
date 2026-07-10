"""Tests for the lean (no-indicator) XS ingestion path."""

from __future__ import annotations

import pandas as pd
import pytest

from btc_tracker_mongodb import lean_pipeline as lp

_INDICATOR_COLS = {"rsi", "macd", "ema_20", "bb_upper", "atr"}   # a few of the 85


def _perp_df():
    idx = pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True)
    idx.name = "timestamp"
    return pd.DataFrame({"Open": [1.0, 2.0], "High": [1.0, 2.0], "Low": [1.0, 2.0],
                         "Close": [1.5, 2.5], "Volume": [10.0, 20.0]}, index=idx)


def _funding_df():
    idx = pd.to_datetime(["2024-01-01T00:00:00Z", "2024-01-01T08:00:00Z"], utc=True)
    idx.name = "timestamp"
    return pd.DataFrame({"funding_rate": [0.0001, -0.0002],
                         "period_start": idx, "interval_hours": [8, 8]}, index=idx)


def test_perp_df_to_docs_is_lean():
    docs = lp.perp_df_to_docs(_perp_df())
    assert len(docs) == 2
    assert set(docs[0]) == {"timestamp", "Open", "High", "Low", "Close", "Volume"}
    assert not (_INDICATOR_COLS & set(docs[0]))       # NO indicator columns
    assert docs[0]["Close"] == 1.5


def test_df_to_docs_empty():
    assert lp.perp_df_to_docs(pd.DataFrame()) == []
    assert lp.funding_df_to_docs(None) == []


def test_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429")
        return "ok"

    assert lp._retry(flaky, tries=3, base=0.0) == "ok"
    assert calls["n"] == 3


def test_retry_reraises_after_exhaustion():
    def always_fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        lp._retry(always_fail, tries=2, base=0.0)


def test_adaptive_fetch_picks_window_with_most_rows(monkeypatch):
    # Mimic KuCoin's predates-listing quirk: too-old windows return FEWER rows, so the
    # adaptive fetch must pick the window that maximises rows (not just the first non-empty).
    rows_by_window = {900: 0, 550: 500, 400: 400, 270: 270, 150: 150, 70: 70}

    def fake_perp(symbol, tf, since_ms, limit):
        w = round((lp._now_ms() - since_ms) / lp.DAY_MS)
        n = rows_by_window.get(min(rows_by_window, key=lambda x: abs(x - w)), 0)
        return pd.DataFrame({"Close": range(n)}) if n else pd.DataFrame()

    monkeypatch.setattr(lp, "fetch_perp_candles", fake_perp)
    best = lp._adaptive_backfill_fetch("HYPE-USDT", "perp")
    assert len(best) == 500      # the 550d window, not the empty 900d nor the smaller ones


def test_lean_ingest_refuses_production_token():
    prod = next(iter(lp.PRODUCTION_SYMBOLS))   # e.g. "BTC-USDT"
    with pytest.raises(ValueError, match="production token"):
        lp.lean_ingest_token(prod)


def test_lean_ingest_token_upserts_lean_docs_no_indicators(monkeypatch):
    captured = {}
    monkeypatch.setattr(lp, "fetch_perp_candles", lambda *a, **k: _perp_df())
    monkeypatch.setattr(lp, "fetch_funding_rate_history", lambda *a, **k: _funding_df())
    monkeypatch.setattr(lp.db, "ensure_indexes", lambda *a, **k: None)
    monkeypatch.setattr(lp.db, "ensure_funding_indexes", lambda *a, **k: None)

    def _cap_perp(symbol, tf, docs, **k):
        captured["perp"] = docs
        return len(docs)

    def _cap_fund(symbol, docs, **k):
        captured["funding"] = docs
        return len(docs)

    monkeypatch.setattr(lp.db, "bulk_upsert", _cap_perp)
    monkeypatch.setattr(lp.db, "bulk_upsert_funding", _cap_fund)

    res = lp.lean_ingest_token("FOO-USDT", incremental=False)
    assert res == {"symbol": "FOO-USDT", "perp": 2, "funding": 2}
    # what got written is lean OHLCV, not indicators
    assert not (_INDICATOR_COLS & set(captured["perp"][0]))
    assert captured["perp"][0]["Close"] == 1.5
    assert "funding_rate" in captured["funding"][0]
