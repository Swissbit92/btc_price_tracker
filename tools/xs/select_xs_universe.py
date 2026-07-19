#!/usr/bin/env python3
"""Select the top-N liquid KuCoin perpetual-futures tokens for the XS research universe.

Ranks USDT-margined perpetual swaps by 24h quote volume and writes the chosen set to
``config/xs_universe.json``. This universe is ingested LEAN (perp-daily OHLCV + funding only,
no 85 indicators) by ``btc_tracker_mongodb/lean_pipeline.py`` and is kept SEPARATE from the
production ``config.TOKENS`` list / launchd jobs — it exists solely to feed CRA's read-only
``engine/xs/`` cross-sectional funding-carry re-test on a wider universe.

Re-runnable as liquidity shifts. Read-only against KuCoin (public API); the only write is the
JSON manifest.

Usage: python tools/xs/select_xs_universe.py [--top-n 300 --out config/xs_universe.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def ccxt_to_tracker_symbol(ccxt_symbol: str) -> str:
    """'BTC/USDT:USDT' -> 'BTC-USDT' (the tracker's dash-form symbol)."""
    base = ccxt_symbol.split("/")[0]
    return f"{base}-USDT"


def select_top_perps(markets: dict, tickers: dict, top_n: int = 300) -> list[dict]:
    """Pure selection logic (no network): rank active USDT-margined perpetual swaps by 24h
    quote volume, return the top-N as tracker-symbol manifest rows. Deterministic — ties
    broken by symbol so re-runs are stable.

    Args:
        markets: ccxt ``load_markets()`` output ({ccxt_symbol: market_dict}).
        tickers: ccxt ``fetch_tickers()`` output ({ccxt_symbol: ticker_dict}).
    """
    rows = []
    for sym, m in markets.items():
        if not (m.get("swap") and m.get("linear") and m.get("active")):
            continue
        if m.get("quote") != "USDT" or m.get("settle") != "USDT":
            continue
        tk = tickers.get(sym) or {}
        qv = tk.get("quoteVolume")
        if qv is None:
            base_vol, last = tk.get("baseVolume"), tk.get("last")
            qv = (base_vol * last) if (base_vol and last) else 0.0
        rows.append({"ccxt_symbol": sym, "symbol": ccxt_to_tracker_symbol(sym),
                     "quote_volume_24h": float(qv or 0.0)})
    rows.sort(key=lambda r: (-r["quote_volume_24h"], r["symbol"]))
    return rows[:top_n]


def _fetch_and_select(top_n: int) -> list[dict]:
    import ccxt

    ex = ccxt.kucoinfutures({"enableRateLimit": True})
    markets = ex.load_markets()
    tickers = ex.fetch_tickers()
    return select_top_perps(markets, tickers, top_n=top_n)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--top-n", type=int, default=300)
    p.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "..",
                                                 "config", "xs_universe.json"))
    args = p.parse_args()

    rows = _fetch_and_select(args.top_n)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"count": len(rows), "top_n": args.top_n, "tokens": rows}, fh, indent=2)
    print(f"selected {len(rows)} perps (top {args.top_n} by 24h quote volume) → {args.out}")
    for r in rows[:10]:
        print(f"  {r['symbol']:16s} ${r['quote_volume_24h']:,.0f}")
    print("  ...")


if __name__ == "__main__":
    main()
