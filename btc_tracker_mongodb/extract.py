"""
extract.py — Fetch OHLCV candles from KuCoin via CCXT.
"""

import time
import ccxt
import pandas as pd
from datetime import datetime, timezone

from .config import TIMEFRAMES, SEED_WINDOW

# Shared exchange instance (public endpoints only, no auth needed)
_exchange = None


def _get_exchange() -> ccxt.kucoin:
    global _exchange
    if _exchange is None:
        _exchange = ccxt.kucoin({"enableRateLimit": True})
        _exchange.load_markets()
    return _exchange


def _normalize_symbol(symbol: str) -> str:
    """Convert 'BTC-USDT' to CCXT format 'BTC/USDT'."""
    return symbol.replace("-", "/")


def _timeframe_ccxt(timeframe: str) -> str:
    """Convert internal timeframe key to CCXT timeframe string."""
    return {"1h": "1h", "1d": "1d"}[timeframe]


def _candle_delta_ms(timeframe: str) -> int:
    """Milliseconds per candle."""
    return {"1h": 3_600_000, "1d": 86_400_000}[timeframe]


def fetch_candles(
    symbol: str,
    timeframe: str,
    since_ms: int,
    limit: int = 500,
) -> pd.DataFrame:
    """Fetch OHLCV candles from KuCoin starting at *since_ms* (epoch ms).

    Returns a DataFrame indexed by UTC timestamp with columns:
    Open, High, Low, Close, Volume.
    """
    ex = _get_exchange()
    ccxt_symbol = _normalize_symbol(symbol)
    ccxt_tf = _timeframe_ccxt(timeframe)

    all_rows = []
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


def fetch_seed_candles(
    symbol: str,
    timeframe: str,
    count: int = SEED_WINDOW,
) -> pd.DataFrame:
    """Fetch the last *count* candles for initial backfill."""
    delta_ms = _candle_delta_ms(timeframe)
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - (count * delta_ms)
    return fetch_candles(symbol, timeframe, since_ms, limit=count)
