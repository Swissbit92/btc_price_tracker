"""One-off script to remove legacy fields from btc_daily_price_data.
Delete this file after verification."""

from btc_tracker_mongodb.db import get_collection
import argparse

LEGACY_FIELDS = ["Moon_Cycle", "Fib_0", "Fib_1", "Stoch_RSI"]


def cleanup(test=False):
    coll = get_collection("BTC-USDT", "1d", test=test)
    query = {"$or": [{f: {"$exists": True}} for f in LEGACY_FIELDS]}
    count = coll.count_documents(query)
    print(f"Found {count} documents with legacy fields in "
          f"{'test' if test else 'prod'}.btc_daily_price_data")
    if count > 0:
        result = coll.update_many({}, {"$unset": {f: "" for f in LEGACY_FIELDS}})
        print(f"Cleaned {result.modified_count} documents")
    else:
        print("Nothing to clean")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove legacy fields from BTC daily")
    parser.add_argument("--test", action="store_true", help="Use test database")
    args = parser.parse_args()
    cleanup(test=args.test)
