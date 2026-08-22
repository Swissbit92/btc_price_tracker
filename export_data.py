#!/usr/bin/env python3
"""
Export all MongoDB crypto price data to CSV files in data/.

Creates a structured backup:
  data/
    spot/     -- per-token spot OHLCV + indicators (daily, weekly, 1h)
    perp/     -- per-token perpetual futures OHLCV + indicators
    funding/  -- per-token 8h funding rate settlements
    metadata/ -- indicator glossary

Usage:
    python export_data.py                    # export all tokens
    python export_data.py --tokens BTC,ETH   # export specific tokens only
    python export_data.py --dry-run          # show what would be exported
"""

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient

from btc_tracker_mongodb.config import DB_NAME, TOKENS

load_dotenv()

BASE_DIR = Path("data")
SPOT_DIR = BASE_DIR / "spot"
PERP_DIR = BASE_DIR / "perp"
FUNDING_DIR = BASE_DIR / "funding"
META_DIR = BASE_DIR / "metadata"


def _get_db():
    uri = os.getenv("MONGODB_URI")
    if not uri:
        print("ERROR: MONGODB_URI not set")
        sys.exit(1)
    return MongoClient(uri)[DB_NAME]


def _fmt_size(nbytes):
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def _export_collection(db, collection_name, csv_path, dry_run=False):
    """Export a single collection to CSV. Returns (rows, bytes)."""
    coll = db[collection_name]
    count = coll.count_documents({})
    if count == 0:
        return 0, 0

    if dry_run:
        print(f"  [DRY RUN] {csv_path.name} -- {count:,} docs")
        return count, 0

    cursor = coll.find({}, {"_id": 0}).sort("timestamp", 1)
    docs = list(cursor)
    df = pd.DataFrame(docs)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df.set_index("timestamp", inplace=True)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path)
    size = csv_path.stat().st_size
    print(f"  {csv_path.name} -- {len(df):,} rows, {_fmt_size(size)}")
    return len(df), size


def main():
    parser = argparse.ArgumentParser(description="Export MongoDB data to CSV backups")
    parser.add_argument("--tokens", type=str, default=None,
                        help="Comma-separated token list (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be exported without writing")
    args = parser.parse_args()

    start = time.time()
    db = _get_db()

    if args.tokens:
        tokens = [t.strip().upper() for t in args.tokens.split(",")]
    else:
        tokens = [sym.split("-")[0] for sym in TOKENS]

    mode = " (DRY RUN)" if args.dry_run else ""
    print(f"\n{'='*55}")
    print(f"  MongoDB -> CSV Export{mode}")
    print(f"  DB: {DB_NAME}")
    print(f"  Tokens: {len(tokens)}")
    print(f"{'='*55}\n")

    total_files = total_rows = total_bytes = 0

    # Spot
    print("[Spot OHLCV]")
    for token in tokens:
        t = token.lower()
        for suffix in ["daily", "weekly", "1h", "4h"]:
            name = f"{t}_{suffix}_price_data"
            if name in db.list_collection_names():
                f_rows, f_bytes = _export_collection(
                    db, name, SPOT_DIR / f"{t}_{suffix}.csv", args.dry_run)
                if f_rows:
                    total_files += 1
                    total_rows += f_rows
                    total_bytes += f_bytes
    print()

    # Perp
    print("[Perpetual Futures OHLCV]")
    for token in tokens:
        t = token.lower()
        for suffix in ["daily", "1h", "4h"]:
            name = f"{t}_perp_{suffix}_price_data"
            if name in db.list_collection_names():
                f_rows, f_bytes = _export_collection(
                    db, name, PERP_DIR / f"{t}_perp_{suffix}.csv", args.dry_run)
                if f_rows:
                    total_files += 1
                    total_rows += f_rows
                    total_bytes += f_bytes
    print()

    # Funding
    print("[Funding Rates]")
    for token in tokens:
        t = token.lower()
        name = f"{t}_funding_rate_data"
        if name in db.list_collection_names():
            f_rows, f_bytes = _export_collection(
                db, name, FUNDING_DIR / f"{t}_funding.csv", args.dry_run)
            if f_rows:
                total_files += 1
                total_rows += f_rows
                total_bytes += f_bytes
    print()

    # Metadata
    print("[Metadata]")
    for meta_name in ["indicator_glossary", "funding_rate_glossary", "token_metadata"]:
        if meta_name in db.list_collection_names():
            f_rows, f_bytes = _export_collection(
                db, meta_name, META_DIR / f"{meta_name}.csv", args.dry_run)
            if f_rows:
                total_files += 1
                total_rows += f_rows
                total_bytes += f_bytes
    print()

    elapsed = time.time() - start
    print(f"{'='*55}")
    print(f"  Export complete in {elapsed:.1f}s")
    print(f"  Files: {total_files}")
    print(f"  Rows:  {total_rows:,}")
    print(f"  Size:  {_fmt_size(total_bytes)}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
