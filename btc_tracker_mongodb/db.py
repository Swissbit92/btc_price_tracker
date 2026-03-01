"""
db.py — MongoDB connection and CRUD operations.
"""

import os
import pandas as pd
from pymongo import MongoClient, UpdateOne, DESCENDING
from dotenv import load_dotenv

from .config import get_collection_name, get_db_name, SLIDING_WINDOW

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


def get_collection(symbol: str, timeframe: str, test: bool = False):
    """Return the pymongo Collection for a given symbol + timeframe."""
    db = get_db(test)
    return db[get_collection_name(symbol, timeframe)]


def load_latest(
    symbol: str,
    timeframe: str,
    limit: int = SLIDING_WINDOW,
    test: bool = False,
) -> pd.DataFrame:
    """Load the last *limit* OHLCV rows from MongoDB, sorted ascending by timestamp."""
    coll = get_collection(symbol, timeframe, test)
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


def get_latest_timestamp(symbol: str, timeframe: str, test: bool = False):
    """Return the most recent timestamp in the collection, or None."""
    coll = get_collection(symbol, timeframe, test)
    doc = coll.find_one({}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", DESCENDING)])
    if doc is None:
        return None
    return pd.to_datetime(doc["timestamp"], utc=True)


def bulk_upsert(
    symbol: str,
    timeframe: str,
    docs: list[dict],
    test: bool = False,
) -> int:
    """Bulk upsert documents keyed by timestamp. Returns number of upserted/modified."""
    if not docs:
        return 0
    coll = get_collection(symbol, timeframe, test)
    ops = [
        UpdateOne({"timestamp": d["timestamp"]}, {"$set": d}, upsert=True)
        for d in docs
    ]
    result = coll.bulk_write(ops, ordered=False)
    return result.upserted_count + result.modified_count


def ensure_indexes(symbol: str, timeframe: str, test: bool = False):
    """Create a unique ascending index on timestamp if it doesn't exist."""
    coll = get_collection(symbol, timeframe, test)
    coll.create_index("timestamp", unique=True)
