"""
mcp_server.py — Read-only MCP server for querying crypto price tracker MongoDB data.

Exposes 6 tools for listing collections, querying price/indicator data,
fetching the indicator glossary, and inspecting collection stats.
"""

import json
import sys
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import DESCENDING, ASCENDING

from mcp.server.fastmcp import FastMCP

# Add project root to path so btc_tracker_mongodb is importable
sys.path.insert(0, ".")

from btc_tracker_mongodb.config import TOKENS, TIMEFRAMES, get_collection_name, METADATA_COLLECTION
from btc_tracker_mongodb.db import get_collection, get_db

mcp = FastMCP("crypto-tracker")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Canonical token names (without -USDT suffix) for flexible input matching
_TOKEN_SET = {t.split("-")[0].upper() for t in TOKENS}


def _serialize(obj):
    """JSON serializer for MongoDB types."""
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _to_json(data) -> str:
    """Serialize data to indented JSON string."""
    return json.dumps(data, default=_serialize, indent=2)


def _normalize_symbol(symbol: str) -> str:
    """Accept 'BTC', 'btc', or 'BTC-USDT' and return 'BTC-USDT'.

    Raises ValueError for unknown tokens.
    """
    s = symbol.strip().upper()
    if s.endswith("-USDT"):
        token = s.replace("-USDT", "")
    else:
        token = s
    if token not in _TOKEN_SET:
        raise ValueError(
            f"Unknown token '{symbol}'. Valid tokens: {sorted(_TOKEN_SET)}"
        )
    return f"{token}-USDT"


def _validate_timeframe(tf: str) -> str:
    """Validate timeframe string. Returns the timeframe or raises ValueError."""
    if tf not in TIMEFRAMES:
        raise ValueError(
            f"Invalid timeframe '{tf}'. Valid timeframes: {list(TIMEFRAMES.keys())}"
        )
    return tf


def _build_projection(fields: str) -> dict:
    """Parse comma-separated field string into a pymongo projection dict.

    Always includes timestamp, always excludes _id.
    """
    proj = {"_id": 0, "timestamp": 1}
    if fields:
        for f in fields.split(","):
            f = f.strip()
            if f and f != "timestamp":
                proj[f] = 1
    return proj


def _parse_datetime(s: str) -> datetime:
    """Parse an ISO date string, defaulting to UTC if naive."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_collections() -> str:
    """List all 39 token/timeframe/collection_name combinations.

    Pure computation from config constants — no MongoDB call required.
    Returns the complete mapping of tokens, timeframes, and collection names.
    """
    try:
        collections = []
        for symbol in TOKENS:
            token = symbol.split("-")[0]
            for tf in TIMEFRAMES:
                collections.append({
                    "token": token,
                    "symbol": symbol,
                    "timeframe": tf,
                    "collection": get_collection_name(symbol, tf),
                })
        return _to_json({
            "tokens": [t.split("-")[0] for t in TOKENS],
            "timeframes": list(TIMEFRAMES.keys()),
            "collections": collections,
            "total": len(collections),
        })
    except Exception as e:
        return _to_json({"error": str(e)})


@mcp.tool()
def query_price_data(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 10,
    fields: str = "",
) -> str:
    """Query latest N documents from a token's price data collection.

    Args:
        symbol: Token symbol — accepts 'BTC', 'btc', or 'BTC-USDT'.
        timeframe: Candle timeframe — '1h', '4h', or '1d'. Default '1h'.
        limit: Number of documents to return (1–200). Default 10.
        fields: Comma-separated field names to include (e.g. 'Close,RSI,MACD_Line').
                Empty string returns all fields.
    """
    try:
        symbol = _normalize_symbol(symbol)
        tf = _validate_timeframe(timeframe)
        limit = max(1, min(200, limit))

        coll = get_collection(symbol, tf)
        proj = _build_projection(fields) if fields else {"_id": 0}
        cursor = coll.find({}, proj).sort("timestamp", DESCENDING).limit(limit)
        docs = list(cursor)

        return _to_json({
            "symbol": symbol,
            "timeframe": tf,
            "count": len(docs),
            "data": docs,
        })
    except Exception as e:
        return _to_json({"error": str(e)})


@mcp.tool()
def get_latest_price(symbol: str, timeframe: str = "1h") -> str:
    """Get the single most recent document for a token.

    Quick snapshot — useful for 'what's the latest BTC price?' style queries.

    Args:
        symbol: Token symbol — accepts 'BTC', 'btc', or 'BTC-USDT'.
        timeframe: Candle timeframe — '1h', '4h', or '1d'. Default '1h'.
    """
    try:
        symbol = _normalize_symbol(symbol)
        tf = _validate_timeframe(timeframe)

        coll = get_collection(symbol, tf)
        doc = coll.find_one({}, {"_id": 0}, sort=[("timestamp", DESCENDING)])
        if doc is None:
            return _to_json({
                "symbol": symbol,
                "timeframe": tf,
                "error": "No data found. Has seed.py been run?",
            })

        return _to_json({
            "symbol": symbol,
            "timeframe": tf,
            "data": doc,
        })
    except Exception as e:
        return _to_json({"error": str(e)})


@mcp.tool()
def get_indicator_glossary() -> str:
    """Fetch the indicator glossary from MongoDB.

    Returns column descriptions, categories, value ranges, dtypes,
    and the schema_hash used for change detection.
    """
    try:
        db = get_db()
        coll = db[METADATA_COLLECTION]
        doc = coll.find_one({"_id": "indicator_glossary"})
        if doc is None:
            return _to_json({
                "error": "Glossary not found. Run a pipeline update to sync it.",
            })
        doc["_id"] = str(doc["_id"])
        return _to_json(doc)
    except Exception as e:
        return _to_json({"error": str(e)})


@mcp.tool()
def get_collection_stats(symbol: str, timeframe: str = "1h") -> str:
    """Get stats for a token's collection: doc count, date range, and column list.

    Useful for understanding data coverage before querying.

    Args:
        symbol: Token symbol — accepts 'BTC', 'btc', or 'BTC-USDT'.
        timeframe: Candle timeframe — '1h', '4h', or '1d'. Default '1h'.
    """
    try:
        symbol = _normalize_symbol(symbol)
        tf = _validate_timeframe(timeframe)

        coll = get_collection(symbol, tf)
        count = coll.estimated_document_count()

        earliest = coll.find_one(
            {}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", ASCENDING)]
        )
        latest = coll.find_one(
            {}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", DESCENDING)]
        )

        # Get column names from the newest document
        columns = []
        newest = coll.find_one({}, sort=[("timestamp", DESCENDING)])
        if newest:
            columns = [k for k in newest.keys() if k != "_id"]

        return _to_json({
            "symbol": symbol,
            "timeframe": tf,
            "collection": get_collection_name(symbol, tf),
            "document_count": count,
            "earliest_timestamp": earliest["timestamp"] if earliest else None,
            "latest_timestamp": latest["timestamp"] if latest else None,
            "columns": columns,
            "column_count": len(columns),
        })
    except Exception as e:
        return _to_json({"error": str(e)})


@mcp.tool()
def query_by_date_range(
    symbol: str,
    start_date: str,
    end_date: str,
    timeframe: str = "1h",
    fields: str = "",
    limit: int = 200,
) -> str:
    """Query documents within a date range (inclusive).

    Results are sorted chronologically (ascending). Useful for analyzing
    indicator behavior over a specific period.

    Args:
        symbol: Token symbol — accepts 'BTC', 'btc', or 'BTC-USDT'.
        start_date: Start date in ISO format (e.g. '2026-03-01' or '2026-03-01T00:00:00').
        end_date: End date in ISO format (e.g. '2026-03-03' or '2026-03-03T23:59:59').
        timeframe: Candle timeframe — '1h', '4h', or '1d'. Default '1h'.
        fields: Comma-separated field names to include. Empty returns all fields.
        limit: Max documents to return (1–500). Default 200.
    """
    try:
        symbol = _normalize_symbol(symbol)
        tf = _validate_timeframe(timeframe)
        limit = max(1, min(500, limit))

        start_dt = _parse_datetime(start_date)
        end_dt = _parse_datetime(end_date)

        coll = get_collection(symbol, tf)
        proj = _build_projection(fields) if fields else {"_id": 0}
        query = {"timestamp": {"$gte": start_dt, "$lte": end_dt}}
        cursor = coll.find(query, proj).sort("timestamp", ASCENDING).limit(limit)
        docs = list(cursor)

        return _to_json({
            "symbol": symbol,
            "timeframe": tf,
            "start_date": start_dt.isoformat(),
            "end_date": end_dt.isoformat(),
            "count": len(docs),
            "limit_applied": limit,
            "data": docs,
        })
    except Exception as e:
        return _to_json({"error": str(e)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
