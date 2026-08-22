"""
db.py — MongoDB connection and CRUD operations.
"""

import os
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
from pymongo import DESCENDING, MongoClient, UpdateOne

from .config import (
    FUNDING_METADATA_COLLECTION,
    METADATA_COLLECTION,
    SLIDING_WINDOW,
    get_collection_name,
    get_db_name,
    get_funding_collection_name,
)

load_dotenv()

_client = None


def _get_client() -> MongoClient:
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI not set")
        _client = MongoClient(uri)
    return _client


def get_db(test: bool = False):
    """Return the pymongo Database for production or test."""
    return _get_client()[get_db_name(test)]


def get_collection(symbol: str, timeframe: str, test: bool = False, market_type: str = "spot"):
    """Return the pymongo Collection for a given symbol + timeframe."""
    db = get_db(test)
    return db[get_collection_name(symbol, timeframe, market_type)]


def load_latest(
    symbol: str,
    timeframe: str,
    limit: int = SLIDING_WINDOW,
    test: bool = False,
    market_type: str = "spot",
) -> pd.DataFrame:
    """Load the last *limit* OHLCV rows from MongoDB, sorted ascending by timestamp."""
    coll = get_collection(symbol, timeframe, test, market_type)
    cursor = (
        coll.find(
            {},
            {"_id": 0, "timestamp": 1, "Open": 1, "High": 1,
             "Low": 1, "Close": 1, "Volume": 1},
        )
        .sort("timestamp", DESCENDING)
        .limit(limit)
    )
    docs = list(cursor)
    if not docs:
        return pd.DataFrame(columns=["timestamp", "Open", "High", "Low", "Close", "Volume"]).set_index("timestamp")
    df = pd.DataFrame(docs)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)
    return df


def get_latest_timestamp(symbol: str, timeframe: str, test: bool = False, market_type: str = "spot"):
    """Return the most recent timestamp in the collection, or None."""
    coll = get_collection(symbol, timeframe, test, market_type)
    doc = coll.find_one({}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", DESCENDING)])
    if doc is None:
        return None
    return pd.to_datetime(doc["timestamp"], utc=True)


def bulk_upsert(
    symbol: str,
    timeframe: str,
    docs: list[dict],
    test: bool = False,
    market_type: str = "spot",
) -> int:
    """Bulk upsert documents keyed by timestamp. Returns number of upserted/modified."""
    if not docs:
        return 0
    coll = get_collection(symbol, timeframe, test, market_type)
    ops = [
        UpdateOne({"timestamp": d["timestamp"]}, {"$set": d}, upsert=True)
        for d in docs
    ]
    result = coll.bulk_write(ops, ordered=False)
    return result.upserted_count + result.modified_count


def load_all(
    symbol: str,
    timeframe: str,
    test: bool = False,
    market_type: str = "spot",
) -> pd.DataFrame:
    """Load ALL documents from a collection (OHLCV columns only).

    Unlike load_latest() which returns the last N rows, this loads everything
    for full-history backfill scenarios where indicators need recomputation.
    """
    coll = get_collection(symbol, timeframe, test, market_type)
    cursor = coll.find(
        {},
        {"_id": 0, "timestamp": 1, "Open": 1, "High": 1,
         "Low": 1, "Close": 1, "Volume": 1},
    ).sort("timestamp", 1)
    docs = list(cursor)
    if not docs:
        return pd.DataFrame(
            columns=["timestamp", "Open", "High", "Low", "Close", "Volume"]
        ).set_index("timestamp")
    df = pd.DataFrame(docs)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.set_index("timestamp", inplace=True)
    return df


def bulk_upsert_chunked(
    symbol: str,
    timeframe: str,
    docs: list[dict],
    test: bool = False,
    market_type: str = "spot",
    chunk_size: int = 5000,
) -> int:
    """Bulk upsert in chunks to handle large collections without memory spikes."""
    if not docs:
        return 0
    coll = get_collection(symbol, timeframe, test, market_type)
    total = 0
    for i in range(0, len(docs), chunk_size):
        chunk = docs[i : i + chunk_size]
        ops = [
            UpdateOne({"timestamp": d["timestamp"]}, {"$set": d}, upsert=True)
            for d in chunk
        ]
        result = coll.bulk_write(ops, ordered=False)
        n = result.upserted_count + result.modified_count
        total += n
        print(f"  [chunk] Upserted {n} docs (batch {i // chunk_size + 1}, "
              f"rows {i + 1}-{i + len(chunk)})")
    return total


def ensure_indexes(symbol: str, timeframe: str, test: bool = False, market_type: str = "spot"):
    """Create a unique ascending index on timestamp if it doesn't exist."""
    coll = get_collection(symbol, timeframe, test, market_type)
    coll.create_index("timestamp", unique=True)


def upsert_indicator_glossary(test: bool = False):
    """Upsert the indicator glossary document into the metadata collection.

    Uses a lazy import of get_glossary_document from indicators to avoid
    circular imports (indicators imports nothing from db).
    """
    from .indicators import get_glossary_document

    doc = get_glossary_document()
    db = get_db(test)
    coll = db[METADATA_COLLECTION]
    coll.update_one(
        {"_id": doc["_id"]},
        {"$set": doc},
        upsert=True,
    )
    print(f"[glossary] Synced indicator glossary to "
          f"{'test' if test else 'prod'}.{METADATA_COLLECTION}")


# ---------------------------------------------------------------------------
# Funding rate helpers
# ---------------------------------------------------------------------------

def get_funding_collection(symbol: str, test: bool = False):
    """Return the pymongo Collection for funding rate data."""
    db = get_db(test)
    return db[get_funding_collection_name(symbol)]


def load_funding_rates(
    symbol: str,
    test: bool = False,
    since=None,
    until=None,
) -> pd.DataFrame:
    """Load funding rate history for a token.

    Args:
        since: Optional datetime — only load rates after this time
        until: Optional datetime — only load rates before this time

    Returns DataFrame with columns: timestamp (index), funding_rate, mark_price,
    index_price, basis_pct, period_start, interval_hours.
    """
    coll = get_funding_collection(symbol, test)
    query = {}
    if since or until:
        query["timestamp"] = {}
        if since:
            query["timestamp"]["$gte"] = since
        if until:
            query["timestamp"]["$lte"] = until
    cursor = coll.find(query, {"_id": 0}).sort("timestamp", 1)
    docs = list(cursor)
    if not docs:
        return pd.DataFrame(columns=[
            "timestamp", "funding_rate", "mark_price", "index_price",
            "basis_pct", "period_start", "interval_hours"
        ]).set_index("timestamp")
    df = pd.DataFrame(docs)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    if "period_start" in df.columns:
        df["period_start"] = pd.to_datetime(df["period_start"], utc=True)
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)
    return df


def bulk_upsert_funding(
    symbol: str,
    docs: list[dict],
    test: bool = False,
) -> int:
    """Bulk upsert funding rate documents keyed by timestamp."""
    if not docs:
        return 0
    coll = get_funding_collection(symbol, test)
    ops = [
        UpdateOne({"timestamp": d["timestamp"]}, {"$set": d}, upsert=True)
        for d in docs
    ]
    result = coll.bulk_write(ops, ordered=False)
    return result.upserted_count + result.modified_count


def ensure_funding_indexes(symbol: str, test: bool = False):
    """Create a unique ascending index on timestamp for funding rate collection."""
    coll = get_funding_collection(symbol, test)
    coll.create_index("timestamp", unique=True)


def upsert_token_metadata(test: bool = False):
    """Upsert per-token metadata and timeframe glossary into token_metadata collection."""
    from .config import TIMEFRAME_GLOSSARY, TOKEN_METADATA, TOKEN_METADATA_COLLECTION

    db = get_db(test)
    coll = db[TOKEN_METADATA_COLLECTION]

    for symbol, meta in TOKEN_METADATA.items():
        token = symbol.split("-")[0].lower()
        doc = {
            "_id": f"{token}_metadata",
            "symbol": symbol,
            "token": token.upper(),
            **meta,
            "updated_at": datetime.now(timezone.utc),
        }
        coll.update_one({"_id": doc["_id"]}, {"$set": doc}, upsert=True)

    tf_doc = {
        "_id": "timeframe_glossary",
        "timeframes": TIMEFRAME_GLOSSARY,
        "updated_at": datetime.now(timezone.utc),
    }
    coll.update_one({"_id": "timeframe_glossary"}, {"$set": tf_doc}, upsert=True)


def upsert_funding_metadata(symbol: str, metadata: dict, test: bool = False):
    """Upsert a funding rate metadata document for a token."""
    db = get_db(test)
    coll = db[FUNDING_METADATA_COLLECTION]
    token = symbol.split("-")[0].lower()
    doc_id = f"{token}_funding"
    metadata["_id"] = doc_id
    metadata["token"] = token.upper()
    coll.update_one(
        {"_id": doc_id},
        {"$set": metadata},
        upsert=True,
    )
