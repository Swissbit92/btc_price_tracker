#!/usr/bin/env python3
"""Lean-ingest the XS research universe (perp-daily OHLCV + funding, no indicators).

Reads the manifest written by ``select_xs_universe.py`` and ingests each token via
``lean_pipeline``. Default = full backfill; ``--incremental`` = refresh only the new bars
(the mode the separate xs-refresh launchd job uses). Writes ONLY additive
``{token}_perp_daily_price_data`` / ``{token}_funding_rate_data`` collections; never touches
the production ``TOKENS`` set, spot collections, or ``strategy_signals``.

Usage:
  python tools/xs/lean_ingest.py                       # full backfill of config/xs_universe.json
  python tools/xs/lean_ingest.py --incremental          # refresh (new bars only)
  python tools/xs/lean_ingest.py --workers 4 --limit 50 # first 50 tokens, 4 processes
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from btc_tracker_mongodb.lean_pipeline import PRODUCTION_SYMBOLS, run_lean_backfill

_DEFAULT_MANIFEST = os.path.join(os.path.dirname(__file__), "..", "..", "config", "xs_universe.json")


def load_universe(path: str) -> list[str]:
    """Load the manifest symbols, EXCLUDING the production TOKENS (maintained by the
    production pipeline — the lean path must never touch their collections)."""
    with open(path) as fh:
        rows = json.load(fh)["tokens"]
    return [r["symbol"] for r in rows if r["symbol"].upper() not in PRODUCTION_SYMBOLS]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", default=_DEFAULT_MANIFEST)
    p.add_argument("--incremental", action="store_true", help="refresh new bars only")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--limit", type=int, default=None, help="ingest only the first N tokens")
    args = p.parse_args()

    symbols = load_universe(args.manifest)
    if args.limit:
        symbols = symbols[: args.limit]
    mode = "incremental refresh" if args.incremental else "full backfill"
    print(f"Lean {mode}: {len(symbols)} tokens, {args.workers} workers ...", flush=True)

    t0 = time.perf_counter()
    results = run_lean_backfill(symbols, incremental=args.incremental, workers=args.workers)
    dt = time.perf_counter() - t0

    ok = [r for r in results if "error" not in r]
    errs = [r for r in results if "error" in r]
    perp_rows = sum(r["perp"] for r in ok)
    fund_rows = sum(r["funding"] for r in ok)
    print(f"\nDone in {dt:.0f}s: {len(ok)}/{len(results)} tokens OK; "
          f"{perp_rows:,} perp rows, {fund_rows:,} funding rows upserted.")
    if errs:
        print(f"  {len(errs)} failed: {', '.join(r['symbol'] for r in errs[:20])}"
              + (" ..." if len(errs) > 20 else ""))


if __name__ == "__main__":
    main()
