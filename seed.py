#!/usr/bin/env python3
"""
seed.py — Root-level entry point for initial data backfill.

Usage:
    python seed.py --symbol BTC-USDT --timeframe 1h [--test]
    python seed.py --symbol BTC-USDT --timeframe 1d --csv daily_history.csv [--test]
    python seed.py --all [--test]
    python seed.py --all --timeframe 1h [--test]
"""

import argparse
from btc_tracker_mongodb.config import TOKENS, TIMEFRAMES
from btc_tracker_mongodb.pipeline import run_seed, run_seed_from_csv, run_seed_all


def main():
    parser = argparse.ArgumentParser(description="Seed price data into MongoDB")
    parser.add_argument("--symbol", help="e.g. BTC-USDT, ETH-USDT")
    parser.add_argument("--timeframe", choices=list(TIMEFRAMES.keys()),
                        help="1h or 1d")
    parser.add_argument("--all", action="store_true",
                        help="Seed all tokens")
    parser.add_argument("--all-timeframes", action="store_true",
                        help="Seed all timeframes for the given symbol")
    parser.add_argument("--test", action="store_true",
                        help="Write to test database instead of production")
    parser.add_argument("--csv", help="Path to CSV file for CSV-based seed")
    parser.add_argument("--count", type=int, default=500,
                        help="Number of candles to fetch (default: 500)")
    args = parser.parse_args()

    if args.all:
        run_seed_all(timeframe=args.timeframe, test=args.test, count=args.count)
        return

    if not args.symbol:
        parser.error("--symbol is required unless --all is used")

    if args.csv:
        tf = args.timeframe or "1d"
        run_seed_from_csv(args.csv, args.symbol, tf, test=args.test)
        return

    if args.all_timeframes:
        for tf in TIMEFRAMES:
            run_seed(args.symbol, tf, test=args.test, count=args.count)
    else:
        tf = args.timeframe or "1h"
        run_seed(args.symbol, tf, test=args.test, count=args.count)


if __name__ == "__main__":
    main()
