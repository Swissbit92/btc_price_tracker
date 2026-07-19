#!/usr/bin/env python3
"""
update.py — Root-level entry point for incremental data updates.

Usage:
    python update.py --symbol BTC-USDT --timeframe 1h [--test]
    python update.py --all --timeframe 1h [--test]
    python update.py --all [--test]
"""

import argparse
from btc_tracker_mongodb.config import TOKENS, TIMEFRAMES, MARKET_TYPES
from btc_tracker_mongodb.pipeline import run_update, run_update_all


def main():
    parser = argparse.ArgumentParser(description="Incremental price data update")
    parser.add_argument("--symbol", help="e.g. BTC-USDT, ETH-USDT")
    parser.add_argument("--timeframe", choices=list(TIMEFRAMES.keys()),
                        help="1h or 1d")
    parser.add_argument("--all", action="store_true",
                        help="Update all tokens")
    parser.add_argument("--all-timeframes", action="store_true",
                        help="Update all timeframes for the given symbol")
    parser.add_argument("--test", action="store_true",
                        help="Read/write test database instead of production")
    parser.add_argument("--market-type", choices=MARKET_TYPES, default="spot",
                        help="Market type: spot (default) or perp (perpetual futures)")
    parser.add_argument("--refresh-last", type=int, default=0, metavar="N",
                        help="Also re-fetch and overwrite the most recent N CLOSED "
                             "candles even though they are already stored. Exchanges "
                             "revise recent candles and the gap check cannot see it.")
    args = parser.parse_args()

    if args.market_type == "perp":
        from btc_tracker_mongodb.pipeline import run_perp_update, run_perp_update_all
        if args.all:
            run_perp_update_all(timeframe=args.timeframe, test=args.test, refresh_last=args.refresh_last)
        elif not args.symbol:
            parser.error("--symbol is required unless --all is used")
        elif args.all_timeframes:
            for tf in TIMEFRAMES:
                run_perp_update(args.symbol, tf, test=args.test, refresh_last=args.refresh_last)
        else:
            tf = args.timeframe or "1h"
            run_perp_update(args.symbol, tf, test=args.test, refresh_last=args.refresh_last)
        return

    if args.all:
        run_update_all(timeframe=args.timeframe, test=args.test, refresh_last=args.refresh_last)
        return

    if not args.symbol:
        parser.error("--symbol is required unless --all is used")

    if args.all_timeframes:
        for tf in TIMEFRAMES:
            run_update(args.symbol, tf, test=args.test, refresh_last=args.refresh_last)
    else:
        tf = args.timeframe or "1h"
        run_update(args.symbol, tf, test=args.test, refresh_last=args.refresh_last)


if __name__ == "__main__":
    main()
