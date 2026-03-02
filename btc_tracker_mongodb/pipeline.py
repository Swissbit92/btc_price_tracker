"""
pipeline.py — Orchestrates the extract -> indicators -> load pipeline.
"""

import pandas as pd
from datetime import datetime, timezone, timedelta

from .config import TOKENS, TIMEFRAMES, SLIDING_WINDOW, SEED_WINDOW
from .db import load_latest, get_latest_timestamp, bulk_upsert, ensure_indexes, upsert_indicator_glossary
from .extract import fetch_candles, fetch_seed_candles
from .indicators import compute_all, get_numeric_cols
from .sentiment import fetch_fear_greed


_glossary_synced = False


def _sync_glossary(test: bool = False):
    """Upsert the indicator glossary once per process lifetime."""
    global _glossary_synced
    if _glossary_synced:
        return
    try:
        upsert_indicator_glossary(test)
    except Exception as e:
        print(f"[glossary] WARNING: failed to sync glossary: {e}")
    _glossary_synced = True


def _timedelta_for(timeframe: str) -> timedelta:
    return {
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
    }[timeframe]


def _floor_timestamp(dt: datetime, timeframe: str) -> datetime:
    """Floor a datetime to the candle boundary."""
    if timeframe == "1h":
        return dt.replace(minute=0, second=0, microsecond=0)
    elif timeframe == "4h":
        return dt.replace(hour=(dt.hour // 4) * 4, minute=0, second=0, microsecond=0)
    else:  # 1d
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _merge_sentiment(docs: list[dict], fng: dict | None) -> list[dict]:
    """Merge Fear & Greed data into each document."""
    if fng is None:
        for doc in docs:
            doc["FnG_Value"] = None
            doc["FnG_Class"] = None
    else:
        for doc in docs:
            doc["FnG_Value"] = fng["FnG_Value"]
            doc["FnG_Class"] = fng["FnG_Class"]
    return docs


def run_seed(symbol: str, timeframe: str, test: bool = False, count: int = SEED_WINDOW):
    """Initial backfill: fetch *count* candles from KuCoin and store them.

    Computes all indicators and drops rows with NaN in required columns.
    """
    _sync_glossary(test)
    print(f"[seed] {symbol} {timeframe} (test={test}) — fetching {count} candles...")
    ensure_indexes(symbol, timeframe, test)

    df = fetch_seed_candles(symbol, timeframe, count=count)
    if df.empty:
        print(f"[seed] No candles returned for {symbol} {timeframe}")
        return

    print(f"[seed] Fetched {len(df)} candles, computing indicators...")
    df = compute_all(df, timeframe)

    # Drop rows where required indicators are NaN
    numeric_cols = get_numeric_cols()
    present_cols = [c for c in numeric_cols if c in df.columns]
    df_clean = df.dropna(subset=present_cols)

    # Fetch Fear & Greed
    fng = fetch_fear_greed()

    docs = _df_to_docs(df_clean)
    docs = _merge_sentiment(docs, fng)
    n = bulk_upsert(symbol, timeframe, docs, test)
    print(f"[seed] Upserted {n} documents into {'test' if test else 'prod'} "
          f"({len(df)} fetched, {len(df_clean)} after NaN drop)")


def run_seed_from_csv(
    csv_path: str,
    symbol: str,
    timeframe: str,
    test: bool = False,
):
    """Seed from a local CSV file (e.g., daily_history.csv)."""
    _sync_glossary(test)
    print(f"[seed-csv] {symbol} {timeframe} from {csv_path} (test={test})")
    ensure_indexes(symbol, timeframe, test)

    df = pd.read_csv(csv_path, skiprows=[1], parse_dates=["Date"])
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["Open", "High", "Low", "Close", "Volume"], inplace=True)
    df["timestamp"] = (
        df["Date"]
        .dt.tz_localize("UTC")
        .apply(lambda dt: dt.replace(hour=0, minute=0, second=0, microsecond=0))
    )
    df = df.set_index("timestamp")[["Open", "High", "Low", "Close", "Volume"]]
    df.sort_index(inplace=True)

    print(f"[seed-csv] Loaded {len(df)} rows, computing indicators...")
    df = compute_all(df, timeframe)

    numeric_cols = get_numeric_cols()
    present_cols = [c for c in numeric_cols if c in df.columns]
    df_clean = df.dropna(subset=present_cols)

    fng = fetch_fear_greed()

    docs = _df_to_docs(df_clean)
    docs = _merge_sentiment(docs, fng)
    n = bulk_upsert(symbol, timeframe, docs, test)
    print(f"[seed-csv] Upserted {n} documents into {'test' if test else 'prod'}")


def run_update(symbol: str, timeframe: str, test: bool = False):
    """Incremental update: detect gaps since last stored timestamp, fetch
    missing candles, recompute indicators on the sliding window, upsert new rows.
    """
    _sync_glossary(test)
    ensure_indexes(symbol, timeframe, test)

    last_ts = get_latest_timestamp(symbol, timeframe, test)
    if last_ts is None:
        print(f"[update] No data for {symbol} {timeframe} — run seed first.")
        return

    now = _floor_timestamp(datetime.now(timezone.utc), timeframe)
    delta = _timedelta_for(timeframe)

    if now <= last_ts:
        print(f"[update] {symbol} {timeframe} — up to date (latest: {last_ts})")
        return

    # Fetch missing candles
    fetch_since_ms = int((last_ts + delta).timestamp() * 1000)
    print(f"[update] {symbol} {timeframe} — gap from {last_ts + delta} to {now}")
    df_missing = fetch_candles(symbol, timeframe, fetch_since_ms)

    if df_missing.empty:
        print(f"[update] No new candles returned for {symbol} {timeframe}")
        return

    # Load sliding window
    df_window = load_latest(symbol, timeframe, limit=SLIDING_WINDOW, test=test)
    if len(df_window) < SLIDING_WINDOW:
        print(f"[update] WARNING: only {len(df_window)} rows in window "
              f"(need {SLIDING_WINDOW} for full indicator accuracy)")

    # Combine and recompute
    df_full = pd.concat([df_window, df_missing])
    df_full = df_full[~df_full.index.duplicated(keep="last")]
    df_full.sort_index(inplace=True)

    df_full = compute_all(df_full, timeframe)

    # Fetch Fear & Greed once per update run
    fng = fetch_fear_greed()

    # Only upsert the newly fetched timestamps (not the window)
    numeric_cols = get_numeric_cols()
    present_cols = [c for c in numeric_cols if c in df_full.columns]
    new_docs = []
    for ts in df_missing.index:
        if ts not in df_full.index:
            continue
        row = df_full.loc[ts]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        if row[present_cols].isna().any():
            print(f"[update] Skipping {ts}: NaN in indicators")
            continue
        doc = row.to_dict()
        doc["timestamp"] = ts
        new_docs.append(doc)

    new_docs = _merge_sentiment(new_docs, fng)
    n = bulk_upsert(symbol, timeframe, new_docs, test)
    print(f"[update] Upserted {n} new candles for {symbol} {timeframe}")


def run_update_all(timeframe: str = None, test: bool = False):
    """Run incremental update for all tokens and timeframes."""
    timeframes = [timeframe] if timeframe else list(TIMEFRAMES.keys())
    for sym in TOKENS:
        for tf in timeframes:
            run_update(sym, tf, test)


def run_seed_all(timeframe: str = None, test: bool = False, count: int = SEED_WINDOW):
    """Run seed for all tokens and timeframes."""
    timeframes = [timeframe] if timeframe else list(TIMEFRAMES.keys())
    for sym in TOKENS:
        for tf in timeframes:
            run_seed(sym, tf, test, count)


def _df_to_docs(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame to a list of dicts with 'timestamp' field."""
    docs = []
    for ts, row in df.iterrows():
        doc = row.to_dict()
        doc["timestamp"] = ts
        docs.append(doc)
    return docs
