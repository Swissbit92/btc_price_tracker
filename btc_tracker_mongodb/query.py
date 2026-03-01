"""
query.py — Parameterized debug query utility.

Usage:
    python -m btc_tracker_mongodb.query --symbol BTC-USDT --timeframe 1h [--test] [--limit 20]
    python -m btc_tracker_mongodb.query --symbol BTC-USDT --timeframe 1h --test --compare
"""

import argparse
import pandas as pd
from .db import get_collection
from .config import get_collection_name


def query_latest(symbol: str, timeframe: str, test: bool = False, limit: int = 10):
    """Print the latest N documents for a given symbol + timeframe."""
    coll = get_collection(symbol, timeframe, test)
    cursor = (
        coll.find({}, {"_id": 0})
        .sort("timestamp", -1)
        .limit(limit)
    )
    docs = list(cursor)
    if not docs:
        print(f"No documents found in {get_collection_name(symbol, timeframe)} "
              f"({'test' if test else 'prod'})")
        return
    df = pd.DataFrame(docs)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.sort_values("timestamp", ascending=False, inplace=True)
    print(f"\n{'TEST' if test else 'PROD'} | {symbol} {timeframe} | "
          f"Collection: {get_collection_name(symbol, timeframe)} | "
          f"Showing latest {len(df)} docs\n")
    print(df.to_string(index=False, max_cols=10))
    print(f"\nTotal columns: {len(df.columns)}")
    print(f"Columns: {list(df.columns)}")


def compare_collections(symbol: str, timeframe: str, limit: int = 20):
    """Compare overlapping OHLCV data between test and prod collections."""
    coll_prod = get_collection(symbol, timeframe, test=False)
    coll_test = get_collection(symbol, timeframe, test=True)

    prod_docs = list(
        coll_prod.find({}, {"_id": 0, "timestamp": 1, "Open": 1, "High": 1,
                            "Low": 1, "Close": 1, "Volume": 1})
        .sort("timestamp", -1).limit(limit)
    )
    test_docs = list(
        coll_test.find({}, {"_id": 0, "timestamp": 1, "Open": 1, "High": 1,
                            "Low": 1, "Close": 1, "Volume": 1})
        .sort("timestamp", -1).limit(limit)
    )

    if not prod_docs:
        print("No production data found.")
        return
    if not test_docs:
        print("No test data found.")
        return

    df_prod = pd.DataFrame(prod_docs).set_index("timestamp")
    df_test = pd.DataFrame(test_docs).set_index("timestamp")

    overlap = df_prod.index.intersection(df_test.index)
    if overlap.empty:
        print("No overlapping timestamps between prod and test.")
        return

    print(f"\nComparing {len(overlap)} overlapping timestamps:\n")
    ohlcv = ["Open", "High", "Low", "Close", "Volume"]
    mismatches = 0
    for ts in sorted(overlap):
        for col in ohlcv:
            p = df_prod.loc[ts, col]
            t = df_test.loc[ts, col]
            if abs(p - t) > 1e-6:
                print(f"  MISMATCH {ts} {col}: prod={p}, test={t}")
                mismatches += 1

    if mismatches == 0:
        print("  All OHLCV values match within tolerance.")
    else:
        print(f"\n  {mismatches} mismatches found.")


def main():
    parser = argparse.ArgumentParser(description="Query price data collections")
    parser.add_argument("--symbol", default="BTC-USDT", help="e.g. BTC-USDT")
    parser.add_argument("--timeframe", default="1h", choices=["1h", "1d"])
    parser.add_argument("--test", action="store_true", help="Query test database")
    parser.add_argument("--limit", type=int, default=10, help="Number of docs to show")
    parser.add_argument("--compare", action="store_true",
                        help="Compare OHLCV between test and prod")
    args = parser.parse_args()

    if args.compare:
        compare_collections(args.symbol, args.timeframe, args.limit)
    else:
        query_latest(args.symbol, args.timeframe, args.test, args.limit)


if __name__ == "__main__":
    main()
