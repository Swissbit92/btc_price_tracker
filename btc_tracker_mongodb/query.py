"""
query.py — Parameterized debug query utility.

Usage:
    python -m btc_tracker_mongodb.query --symbol BTC-USDT --timeframe 1h [--test] [--limit 20]
    python -m btc_tracker_mongodb.query --symbol BTC-USDT --timeframe 1h --test --compare
    python -m btc_tracker_mongodb.query --glossary [--test]
"""

import argparse

import pandas as pd

from .config import METADATA_COLLECTION, get_collection_name
from .db import get_collection, get_db


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


def query_glossary(test: bool = False):
    """Fetch and pretty-print the indicator glossary from MongoDB."""
    db = get_db(test)
    doc = db[METADATA_COLLECTION].find_one({"_id": "indicator_glossary"})
    if doc is None:
        print("No glossary document found. Run seed or update first to sync it.")
        return

    print(f"\n{'TEST' if test else 'PROD'} | Indicator Glossary")
    print(f"Schema hash : {doc.get('schema_hash', 'N/A')[:16]}...")
    print(f"Updated at  : {doc.get('updated_at', 'N/A')}")
    print(f"Total cols  : {doc.get('total_columns', 'N/A')} "
          f"({doc.get('total_numeric', '?')} numeric, "
          f"{doc.get('total_string', '?')} string)\n")

    for cat in doc.get("categories", []):
        print(f"  {cat['name']} ({cat['count']} columns)")
        for col in cat["columns"]:
            meta = doc.get("indicators", {}).get(col, {})
            desc = meta.get("description", "")
            rng = meta.get("range", "")
            print(f"    {col:<25} [{rng}]  {desc[:80]}")
        print()


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
    parser.add_argument("--timeframe", default="1h", choices=["1h", "4h", "1d"])
    parser.add_argument("--test", action="store_true", help="Query test database")
    parser.add_argument("--limit", type=int, default=10, help="Number of docs to show")
    parser.add_argument("--compare", action="store_true",
                        help="Compare OHLCV between test and prod")
    parser.add_argument("--glossary", action="store_true",
                        help="Show the indicator glossary from MongoDB")
    args = parser.parse_args()

    if args.glossary:
        query_glossary(args.test)
    elif args.compare:
        compare_collections(args.symbol, args.timeframe, args.limit)
    else:
        query_latest(args.symbol, args.timeframe, args.test, args.limit)


if __name__ == "__main__":
    main()
