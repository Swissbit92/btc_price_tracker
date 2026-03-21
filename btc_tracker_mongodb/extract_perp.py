"""
extract_perp.py — Fetch perpetual futures OHLCV candles and funding rate
history from KuCoin Futures via CCXT.
"""

import time
import ccxt
import pandas as pd
from datetime import datetime, timezone, timedelta

from .config import SEED_WINDOW, PERP_SYMBOL_MAP

# ---------------------------------------------------------------------------
# Shared futures exchange instance (public endpoints only, no auth needed)
# ---------------------------------------------------------------------------
_exchange_futures = None


def _get_futures_exchange() -> ccxt.kucoinfutures:
    global _exchange_futures
    if _exchange_futures is None:
        _exchange_futures = ccxt.kucoinfutures({"enableRateLimit": True})
        _exchange_futures.load_markets()
    return _exchange_futures


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_perp_symbol(symbol: str) -> str:
    """Convert 'BTC-USDT' to CCXT futures format 'BTC/USDT:USDT'."""
    return PERP_SYMBOL_MAP.get(symbol, symbol.replace("-", "/") + ":USDT")


def _timeframe_ccxt(timeframe: str) -> str:
    """Convert internal timeframe key to CCXT timeframe string."""
    return {"1h": "1h", "4h": "4h", "1d": "1d"}[timeframe]


def _candle_delta_ms(timeframe: str) -> int:
    """Milliseconds per candle."""
    return {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}[timeframe]


# ---------------------------------------------------------------------------
# OHLCV
# ---------------------------------------------------------------------------

def fetch_perp_candles(
    symbol: str,
    timeframe: str,
    since_ms: int,
    limit: int = 500,
) -> pd.DataFrame:
    """Fetch perpetual futures OHLCV candles starting at *since_ms* (epoch ms).

    Returns a DataFrame indexed by UTC timestamp with columns:
    Open, High, Low, Close, Volume.
    """
    ex = _get_futures_exchange()
    ccxt_symbol = _normalize_perp_symbol(symbol)
    ccxt_tf = _timeframe_ccxt(timeframe)

    all_rows: list[dict] = []
    cursor = since_ms
    remaining = limit

    while remaining > 0:
        batch_size = min(remaining, 500)  # KuCoin max per request
        ohlcv = ex.fetch_ohlcv(ccxt_symbol, ccxt_tf, since=cursor, limit=batch_size)
        if not ohlcv:
            break
        for row in ohlcv:
            ts_ms, o, h, l, c, v = row
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            all_rows.append({
                "timestamp": dt,
                "Open": float(o),
                "High": float(h),
                "Low": float(l),
                "Close": float(c),
                "Volume": float(v),
            })
        # Advance cursor past last candle
        cursor = ohlcv[-1][0] + _candle_delta_ms(timeframe)
        remaining -= len(ohlcv)
        if len(ohlcv) < batch_size:
            break  # no more data available

    if not all_rows:
        return pd.DataFrame(
            columns=["timestamp", "Open", "High", "Low", "Close", "Volume"]
        ).set_index("timestamp")

    df = pd.DataFrame(all_rows)
    df.set_index("timestamp", inplace=True)
    df = df[~df.index.duplicated(keep="last")]
    df.sort_index(inplace=True)
    return df


def fetch_perp_seed_candles(
    symbol: str,
    timeframe: str,
    count: int = SEED_WINDOW,
) -> pd.DataFrame:
    """Fetch the last *count* perpetual futures candles for initial backfill."""
    delta_ms = _candle_delta_ms(timeframe)
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - (count * delta_ms)
    return fetch_perp_candles(symbol, timeframe, since_ms, limit=count)


# ---------------------------------------------------------------------------
# Funding rates
# ---------------------------------------------------------------------------

def fetch_funding_rate_history(
    symbol: str,
    since_ms: int | None = None,
    limit: int = 500,
) -> pd.DataFrame:
    """Fetch funding rate history for a perpetual futures contract.

    Paginates through the exchange's funding rate endpoint, collecting up to
    *limit* records starting from *since_ms* (epoch milliseconds).

    Returns a DataFrame indexed by UTC timestamp (settlement time) with columns:
        period_start    — start of the funding period (settlement minus interval)
        funding_rate    — rate as float (e.g. 0.0001 = 0.01% per period)
        mark_price      — mark price at settlement (None if unavailable)
        index_price     — index/spot price at settlement (None if unavailable)
        basis_pct       — (mark - index) / index * 100 (None if prices absent)
        interval_hours  — interval in hours (derived from consecutive records)
    """
    ex = _get_futures_exchange()
    ccxt_symbol = _normalize_perp_symbol(symbol)

    all_records: list[dict] = []
    cursor = since_ms
    remaining = limit
    batch_size = 100  # funding rate endpoint has lower limit than OHLCV

    while remaining > 0:
        fetch_limit = min(remaining, batch_size)
        records = ex.fetch_funding_rate_history(
            ccxt_symbol, since=cursor, limit=fetch_limit
        )
        if not records:
            break

        for rec in records:
            all_records.append(rec)

        # Advance cursor past last record (+1ms, not fixed interval)
        cursor = records[-1]["timestamp"] + 1
        remaining -= len(records)
        if len(records) < fetch_limit:
            break  # no more data available

    if not all_records:
        return pd.DataFrame(
            columns=[
                "timestamp", "period_start", "funding_rate",
                "mark_price", "index_price", "basis_pct", "interval_hours",
            ]
        ).set_index("timestamp")

    # Build rows with derived fields
    rows: list[dict] = []
    for i, rec in enumerate(all_records):
        ts_ms = rec["timestamp"]
        settlement_dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)

        funding_rate = rec.get("fundingRate")
        mark_price = rec.get("markPrice")
        index_price = rec.get("indexPrice")

        # Compute basis_pct
        basis_pct = None
        if mark_price is not None and index_price is not None and index_price != 0:
            basis_pct = (mark_price - index_price) / index_price * 100

        # Determine interval_hours from consecutive records
        if i > 0:
            prev_ts_ms = all_records[i - 1]["timestamp"]
            interval_ms = ts_ms - prev_ts_ms
            interval_hours = interval_ms / 3_600_000
        else:
            # First record: look ahead if possible, otherwise None (unknown)
            if len(all_records) > 1:
                next_ts_ms = all_records[1]["timestamp"]
                interval_ms = next_ts_ms - ts_ms
                interval_hours = interval_ms / 3_600_000
            else:
                interval_hours = None

        # period_start = settlement time minus interval (None if interval unknown)
        if interval_hours is not None:
            period_start = settlement_dt - timedelta(hours=interval_hours)
        else:
            period_start = None

        rows.append({
            "timestamp": settlement_dt,
            "period_start": period_start,
            "funding_rate": float(funding_rate) if funding_rate is not None else None,
            "mark_price": float(mark_price) if mark_price is not None else None,
            "index_price": float(index_price) if index_price is not None else None,
            "basis_pct": float(basis_pct) if basis_pct is not None else None,
            "interval_hours": float(interval_hours) if interval_hours is not None else None,
        })

    df = pd.DataFrame(rows)
    df.set_index("timestamp", inplace=True)
    df = df[~df.index.duplicated(keep="last")]
    df.sort_index(inplace=True)
    return df
