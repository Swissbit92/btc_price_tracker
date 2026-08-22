#!/usr/bin/env python3
"""
backfill.py — Deep historical data backfill from KuCoin.

Fetches max available history, merges with existing MongoDB data,
recomputes all indicators, and upserts the full dataset.

Time limits:
  - Daily (1d): Max available (back to ~Oct 2017 or token listing date)
  - 4h:         Capped at 2020-01-01
  - 1h:         Capped at 2020-01-01

Usage:
    python backfill.py --symbol ETH-USDT --timeframe 1d --test --dry-run
    python backfill.py --symbol ETH-USDT --timeframe 1d --test
    python backfill.py --all --timeframe 1d --test --skip-btc
    python backfill.py --all --test
    python backfill.py --all --timeframe 1d --skip-btc
"""

import argparse

from btc_tracker_mongodb.config import MARKET_TYPES, TIMEFRAMES
from btc_tracker_mongodb.pipeline import run_backfill, run_backfill_all


def main():
    parser = argparse.ArgumentParser(
        description="Deep historical backfill from KuCoin into MongoDB"
    )
    parser.add_argument("--symbol", help="e.g. ETH-USDT, SOL-USDT")
    parser.add_argument("--timeframe", choices=list(TIMEFRAMES.keys()),
                        help="1h, 4h, or 1d")
    parser.add_argument("--all", action="store_true",
                        help="Backfill all tokens")
    parser.add_argument("--all-timeframes", action="store_true",
                        help="Backfill all timeframes for the given symbol")
    parser.add_argument("--test", action="store_true",
                        help="Write to test database instead of production")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and compute but don't write to MongoDB")
    parser.add_argument("--skip-btc", action="store_true",
                        help="Skip BTC when using --all (BTC already has deep history)")
    parser.add_argument("--since",
                        help="Override start date as YYYY-MM-DD (e.g. 2017-10-01)")
    parser.add_argument("--market-type", choices=MARKET_TYPES, default="spot",
                        help="Market type: spot (default) or perp (perpetual futures)")
    args = parser.parse_args()

    if args.market_type == "perp":
        from btc_tracker_mongodb.pipeline import run_perp_backfill, run_perp_backfill_all
        if args.all:
            run_perp_backfill_all(
                timeframe=args.timeframe,
                test=args.test,
                dry_run=args.dry_run,
                skip_btc=args.skip_btc,
                since=args.since,
            )
        elif not args.symbol:
            parser.error("--symbol is required unless --all is used")
        elif args.all_timeframes:
            for tf in ["1d", "4h", "1h"]:
                run_perp_backfill(args.symbol, tf, test=args.test, dry_run=args.dry_run, since=args.since)
        else:
            tf = args.timeframe or "1d"
            run_perp_backfill(args.symbol, tf, test=args.test, dry_run=args.dry_run, since=args.since)
        return

    if args.all:
        run_backfill_all(
            timeframe=args.timeframe,
            test=args.test,
            dry_run=args.dry_run,
            skip_btc=args.skip_btc,
            since=args.since,
        )
        return

    if not args.symbol:
        parser.error("--symbol is required unless --all is used")

    if args.all_timeframes:
        for tf in ["1d", "4h", "1h"]:
            run_backfill(args.symbol, tf, test=args.test, dry_run=args.dry_run, since=args.since)
    else:
        tf = args.timeframe or "1d"
        run_backfill(args.symbol, tf, test=args.test, dry_run=args.dry_run, since=args.since)


if __name__ == "__main__":
    main()
