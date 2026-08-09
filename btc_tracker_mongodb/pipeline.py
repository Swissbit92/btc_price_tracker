"""
pipeline.py — Orchestrates the extract -> indicators -> load pipeline.
"""

import pandas as pd
from datetime import datetime, timezone, timedelta

from .config import TOKENS, TIMEFRAMES, SLIDING_WINDOW, SEED_WINDOW
from .db import (load_latest, load_all, get_latest_timestamp,
                 bulk_upsert, bulk_upsert_chunked, ensure_indexes, upsert_indicator_glossary,
                 upsert_token_metadata, bulk_upsert_funding, ensure_funding_indexes,
                 get_funding_collection)
from .extract import fetch_candles, fetch_seed_candles
from .extract_perp import fetch_perp_candles, fetch_perp_seed_candles, fetch_funding_rate_history
from .indicators import compute_all, get_numeric_cols
from .sentiment import fetch_fear_greed


_glossary_synced = False


def _sync_glossary(test: bool = False):
    """Upsert the indicator glossary and token metadata once per process lifetime."""
    global _glossary_synced
    if _glossary_synced:
        return
    try:
        upsert_indicator_glossary(test)
        upsert_token_metadata(test)
    except Exception as e:
        print(f"[glossary] WARNING: failed to sync glossary: {e}")
    _glossary_synced = True


def _timedelta_for(timeframe: str) -> timedelta:
    return {
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
        "1w": timedelta(weeks=1),
    }[timeframe]


def _floor_timestamp(dt: datetime, timeframe: str) -> datetime:
    """Floor a datetime to the candle boundary."""
    if timeframe == "1h":
        return dt.replace(minute=0, second=0, microsecond=0)
    elif timeframe == "4h":
        return dt.replace(hour=(dt.hour // 4) * 4, minute=0, second=0, microsecond=0)
    elif timeframe == "1w":
        # Floor to the exchange's weekly boundary, which is epoch-anchored, NOT
        # the ISO week. KuCoin buckets weekly candles by epoch modulo, and the
        # Unix epoch (1970-01-01) was a Thursday, so weeks open Thursday 00:00
        # UTC. ccxt does the same in its own `round_timeframe`, and deliberately
        # never re-cuts venue boundaries, so what we store is whatever KuCoin
        # served: every stored weekly bar satisfies `ts % 604800 == 0`.
        #
        # This previously floored to Monday. That is the ISO convention (and
        # what Binance/TradingView use), but it is 4 days off KuCoin's anchor,
        # so `_last_closed_period` returned a cutoff behind the newest stored
        # bar and `run_update` took its "up to date" early-return without ever
        # fetching. Weekly data sat ~2 weeks behind from 2026-07-19 until this
        # fix, unnoticed because the watchdog excludes weekly.
        week = int(_timedelta_for("1w").total_seconds())
        ts = int(dt.timestamp())
        return datetime.fromtimestamp(ts - (ts % week), tz=timezone.utc)
    else:  # 1d
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _last_closed_period(dt: datetime, timeframe: str) -> datetime:
    """Start of the newest candle that has FULLY closed at `dt`.

    ``_floor_timestamp`` returns the start of the candle currently forming, which
    is one period too new for anything that writes to the database. Exchanges
    return the in-progress candle from ``fetch_ohlcv`` like any other, so storing
    what the floor points at freezes a partial bar: the daily job at 23:10 UTC
    was writing that day's candle 50 minutes early, and the hourly job at :05 was
    writing each hour with five minutes of trading in it. Neither was ever
    refreshed, because the next run's gap check saw the timestamp as already
    stored.
    """
    return _floor_timestamp(dt, timeframe) - _timedelta_for(timeframe)


def _drop_unclosed(df, timeframe: str, now: datetime | None = None):
    """Drop any candle whose period has not closed yet.

    Belt-and-braces alongside the fetch-window bound: an exchange is free to
    return a candle we did not ask for, and one partial row silently poisons
    every rolling indicator computed from it thereafter.
    """
    if df is None or df.empty:
        return df
    cutoff = _last_closed_period(now or datetime.now(timezone.utc), timeframe)
    return df[df.index <= cutoff]


def _validatable_cols(df) -> list[str]:
    """Numeric indicator cols that have at least one non-NaN value.

    Columns that are entirely NaN (insufficient history for that indicator)
    are excluded so they don't cause all rows to be dropped.
    """
    numeric_cols = get_numeric_cols()
    present = [c for c in numeric_cols if c in df.columns]
    return [c for c in present if not df[c].isna().all()]


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

    # Drop rows where computable indicators are NaN (excludes all-NaN columns
    # from tokens with insufficient history for long-window indicators)
    valid_cols = _validatable_cols(df)
    df_clean = df.dropna(subset=valid_cols)

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

    valid_cols = _validatable_cols(df)
    df_clean = df.dropna(subset=valid_cols)

    fng = fetch_fear_greed()

    docs = _df_to_docs(df_clean)
    docs = _merge_sentiment(docs, fng)
    n = bulk_upsert(symbol, timeframe, docs, test)
    print(f"[seed-csv] Upserted {n} documents into {'test' if test else 'prod'}")


def run_update(symbol: str, timeframe: str, test: bool = False, refresh_last: int = 0):
    """Incremental update: detect gaps since last stored timestamp, fetch
    missing candles, recompute indicators on the sliding window, upsert new rows.

    Only CLOSED candles are ever written — see ``_last_closed_period``.

    `refresh_last` re-fetches and overwrites the most recent N closed candles
    even though they are already stored. Exchanges do revise recent candles, and
    the gap check alone can never notice because it only looks at the newest
    stored timestamp. Costs one extra fetch per token per run.
    """
    _sync_glossary(test)
    ensure_indexes(symbol, timeframe, test)

    last_ts = get_latest_timestamp(symbol, timeframe, test)
    if last_ts is None:
        print(f"[update] No data for {symbol} {timeframe} — run seed first.")
        return

    now = datetime.now(timezone.utc)
    last_closed = _last_closed_period(now, timeframe)
    delta = _timedelta_for(timeframe)

    fetch_from = last_ts + delta
    if refresh_last > 0:
        fetch_from = min(fetch_from, last_closed - (refresh_last - 1) * delta)

    if fetch_from > last_closed:
        print(f"[update] {symbol} {timeframe} — up to date (latest closed: {last_closed})")
        return

    # Fetch missing candles
    fetch_since_ms = int(fetch_from.timestamp() * 1000)
    print(f"[update] {symbol} {timeframe} — gap from {fetch_from} to {last_closed}")
    df_missing = fetch_candles(symbol, timeframe, fetch_since_ms)
    df_missing = _drop_unclosed(df_missing, timeframe, now)

    if df_missing.empty:
        print(f"[update] No new closed candles for {symbol} {timeframe}")
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
    valid_cols = _validatable_cols(df_full)
    new_docs = []
    for ts in df_missing.index:
        if ts not in df_full.index:
            continue
        row = df_full.loc[ts]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        if row[valid_cols].isna().any():
            print(f"[update] Skipping {ts}: NaN in indicators")
            continue
        doc = row.to_dict()
        doc["timestamp"] = ts
        new_docs.append(doc)

    new_docs = _merge_sentiment(new_docs, fng)
    n = bulk_upsert(symbol, timeframe, new_docs, test)
    print(f"[update] Upserted {n} new candles for {symbol} {timeframe}")


def run_update_all(timeframe: str = None, test: bool = False, refresh_last: int = 0):
    """Run incremental update for all tokens and timeframes."""
    timeframes = [timeframe] if timeframe else list(TIMEFRAMES.keys())
    for sym in TOKENS:
        for tf in timeframes:
            try:
                run_update(sym, tf, test, refresh_last=refresh_last)
            except Exception as e:
                print(f"[update] ERROR: {sym} {tf} failed: {e}")


def run_seed_all(timeframe: str = None, test: bool = False, count: int = SEED_WINDOW):
    """Run seed for all tokens and timeframes."""
    timeframes = [timeframe] if timeframe else list(TIMEFRAMES.keys())
    for sym in TOKENS:
        for tf in timeframes:
            try:
                run_seed(sym, tf, test, count)
            except Exception as e:
                print(f"[seed] ERROR: {sym} {tf} failed: {e}")


def run_backfill(
    symbol: str,
    timeframe: str,
    test: bool = False,
    dry_run: bool = False,
    since: str = None,
):
    """Deep historical backfill for a single token/timeframe.

    Fetches max available history from KuCoin, merges with existing data,
    recomputes all indicators, and upserts the full dataset.

    Args:
        since: Optional override start date as 'YYYY-MM-DD'. If not provided,
               defaults to Oct 2017 for daily, Jan 2020 for 4h/1h.
    """
    _sync_glossary(test)
    ensure_indexes(symbol, timeframe, test)

    # Determine start date
    if since:
        since_dt = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    elif timeframe == "1d":
        since_dt = datetime(2017, 10, 1, tzinfo=timezone.utc)
    else:
        since_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)

    print(f"[backfill] {symbol} {timeframe} (test={test}, dry_run={dry_run})")
    print(f"[backfill] Fetching from {since_dt.date()} — this may take several minutes...")

    # Step 1: Fetch all candles from KuCoin in an outer loop.
    # fetch_candles() may stop early on partial batches, so we keep advancing
    # the cursor and calling again until we've reached the present.
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    delta_ms = int(_timedelta_for(timeframe).total_seconds() * 1000)
    cursor_ms = int(since_dt.timestamp() * 1000)
    all_dfs = []
    empty_streak = 0

    while cursor_ms < now_ms:
        df_batch = fetch_candles(symbol, timeframe, cursor_ms, limit=1500)
        if df_batch.empty:
            # Jump forward 180 days and retry (tokens may be listed years after start date)
            cursor_ms += 180 * 86_400_000
            empty_streak += 1
            if empty_streak >= 20:
                break  # Exhausted search range — stop
            continue
        empty_streak = 0
        all_dfs.append(df_batch)
        last_ts_ms = int(df_batch.index.max().timestamp() * 1000)
        cursor_ms = last_ts_ms + delta_ms
        print(f"  [fetch] {len(df_batch)} candles through {df_batch.index.max().date()} "
              f"(total so far: {sum(len(d) for d in all_dfs)})")

    if not all_dfs:
        print(f"[backfill] No candles returned from exchange for {symbol} {timeframe}")
        return

    df_exchange = pd.concat(all_dfs)
    df_exchange = df_exchange[~df_exchange.index.duplicated(keep="last")]
    df_exchange.sort_index(inplace=True)
    print(f"[backfill] Fetched {len(df_exchange)} total candles from exchange "
          f"({df_exchange.index.min().date()} to {df_exchange.index.max().date()})")

    # Step 2: Load all existing data (OHLCV only)
    df_existing = load_all(symbol, timeframe, test)
    if not df_existing.empty:
        print(f"[backfill] Loaded {len(df_existing)} existing docs from MongoDB")
    else:
        print(f"[backfill] No existing data in MongoDB")

    # Step 3: Merge — existing OHLCV wins on duplicate timestamps
    if not df_existing.empty:
        df_merged = pd.concat([df_exchange, df_existing])
        df_merged = df_merged[~df_merged.index.duplicated(keep="last")]
    else:
        df_merged = df_exchange
    df_merged.sort_index(inplace=True)
    print(f"[backfill] Merged dataset: {len(df_merged)} rows")

    # Step 4: Recompute all indicators
    print(f"[backfill] Computing indicators...")
    df_merged = compute_all(df_merged, timeframe)

    # Step 5: Drop NaN warmup rows (excludes all-NaN columns from short-history tokens)
    valid_cols = _validatable_cols(df_merged)
    df_clean = df_merged.dropna(subset=valid_cols)
    print(f"[backfill] {len(df_clean)} rows after NaN drop "
          f"({len(df_merged) - len(df_clean)} warmup rows removed)")

    # Step 6: Set FnG to None (historical FnG not available)
    docs = _df_to_docs(df_clean)
    for doc in docs:
        doc["FnG_Value"] = None
        doc["FnG_Class"] = None

    if dry_run:
        print(f"[backfill] DRY RUN — would upsert {len(docs)} documents. Skipping write.")
        return

    # Step 7: Upsert in chunks
    print(f"[backfill] Upserting {len(docs)} documents...")
    n = bulk_upsert_chunked(symbol, timeframe, docs, test)
    print(f"[backfill] Done — upserted {n} documents for {symbol} {timeframe}")


def run_backfill_all(
    timeframe: str = None,
    test: bool = False,
    dry_run: bool = False,
    skip_btc: bool = False,
    since: str = None,
):
    """Run backfill for all tokens. Process order: 1w -> 1d -> 4h -> 1h."""
    tf_order = ["1w", "1d", "4h", "1h"]
    timeframes = [timeframe] if timeframe else tf_order
    timeframes = [tf for tf in tf_order if tf in timeframes]

    tokens = [t for t in TOKENS if not (skip_btc and t == "BTC-USDT")]

    total = len(tokens) * len(timeframes)
    done = 0
    failed = []

    for tf in timeframes:
        for sym in tokens:
            done += 1
            print(f"\n{'='*60}")
            print(f"[backfill] [{done}/{total}] {sym} {tf}")
            print(f"{'='*60}")
            try:
                run_backfill(sym, tf, test=test, dry_run=dry_run, since=since)
            except Exception as e:
                print(f"[backfill] ERROR: {sym} {tf} failed: {e}")
                failed.append(f"{sym} {tf}")

    print(f"\n[backfill] Complete: {done - len(failed)}/{total} succeeded")
    if failed:
        print(f"[backfill] Failed: {', '.join(failed)}")


def _df_to_docs(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame to a list of dicts with 'timestamp' field."""
    docs = []
    for ts, row in df.iterrows():
        doc = row.to_dict()
        doc["timestamp"] = ts
        docs.append(doc)
    return docs


# ---------------------------------------------------------------------------
# Perpetual Futures — seed / update / backfill
# ---------------------------------------------------------------------------

_THREE_DAYS_MS = 3 * 24 * 60 * 60 * 1000


def _get_funding_since_ms(symbol: str, test: bool, fallback_ms: int) -> int:
    """Return the since_ms to use for an incremental funding rate fetch.

    KuCoin's funding history API has a ~2-day delay: querying with since >= (now - 2d)
    returns 0 records silently. To stay outside that dead zone, we start 3 days
    behind the last stored funding timestamp. Upsert idempotency absorbs the overlap.
    Falls back to fallback_ms (the OHLCV gap start) when no stored data exists.
    """
    coll = get_funding_collection(symbol, test)
    doc = coll.find_one({}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", -1)])
    if doc is None:
        return fallback_ms
    ts = doc["timestamp"]
    last_ms = int(ts.timestamp() * 1000) if hasattr(ts, "timestamp") else int(ts)
    return max(0, last_ms - _THREE_DAYS_MS)


def _fetch_and_store_funding(
    symbol: str,
    since_ms: int,
    test: bool,
    tag: str = "perp",
    limit: int = 500,
):
    """Fetch funding rate history and upsert into the funding collection.

    Raw 8h funding rates are stored separately in {token}_funding_rate_data.
    The consumer (Crypto_Research_Assistant) aggregates them per-timeframe
    via its own merge_funding_to_ohlcv() loader function.

    Follows the same graceful-fallback pattern as FnG.
    """
    try:
        funding_df = fetch_funding_rate_history(symbol, since_ms=since_ms, limit=limit)
        if not funding_df.empty:
            funding_docs_raw = []
            for ts, row in funding_df.iterrows():
                doc = row.to_dict()
                doc["timestamp"] = ts
                funding_docs_raw.append(doc)
            n_funding = bulk_upsert_funding(symbol, funding_docs_raw, test)
            print(f"[{tag}] Stored {n_funding} funding rate records")
        else:
            print(f"[{tag}] No new funding rate records (KuCoin returned empty)")
    except Exception as e:
        print(f"[{tag}] WARNING: funding rate fetch failed: {e}")


def run_perp_seed(
    symbol: str,
    timeframe: str,
    test: bool = False,
    count: int = SEED_WINDOW,
):
    """Seed perpetual futures OHLCV with indicators.

    Also fetches and stores raw funding rates in a separate collection.
    Funding rate aggregation into OHLCV is the consumer's responsibility.
    """
    _sync_glossary(test)
    print(f"[perp-seed] {symbol} {timeframe} (test={test}) — fetching {count} candles...")
    ensure_indexes(symbol, timeframe, test, market_type="perp")
    ensure_funding_indexes(symbol, test)

    # 1. Fetch perp OHLCV
    df = fetch_perp_seed_candles(symbol, timeframe, count=count)
    if df.empty:
        print(f"[perp-seed] No candles returned for {symbol} {timeframe}")
        return

    # 2. Fetch and store raw funding rates (separate collection)
    since_ms = int(df.index.min().timestamp() * 1000)
    _fetch_and_store_funding(symbol, since_ms, test, tag="perp-seed")

    # 3. Compute indicators
    print(f"[perp-seed] Fetched {len(df)} candles, computing indicators...")
    df = compute_all(df, timeframe)

    # 4. Drop NaN rows (excludes all-NaN columns from short-history tokens)
    valid_cols = _validatable_cols(df)
    df_clean = df.dropna(subset=valid_cols)

    # 5. Sentiment
    fng = fetch_fear_greed()

    # 6. Build docs, merge sentiment
    docs = _df_to_docs(df_clean)
    docs = _merge_sentiment(docs, fng)

    n = bulk_upsert(symbol, timeframe, docs, test, market_type="perp")
    print(f"[perp-seed] Upserted {n} documents into {'test' if test else 'prod'} "
          f"({len(df)} fetched, {len(df_clean)} after NaN drop)")


def run_perp_update(symbol: str, timeframe: str, test: bool = False, refresh_last: int = 0):
    """Incremental update for perpetual futures: detect gaps, fetch missing
    candles, recompute indicators on the sliding window, upsert new rows.

    Also fetches and stores raw funding rates in a separate collection.
    """
    _sync_glossary(test)
    ensure_indexes(symbol, timeframe, test, market_type="perp")
    ensure_funding_indexes(symbol, test)

    last_ts = get_latest_timestamp(symbol, timeframe, test, market_type="perp")
    if last_ts is None:
        print(f"[perp-update] No data for {symbol} {timeframe} — run perp seed first.")
        return

    now = datetime.now(timezone.utc)
    last_closed = _last_closed_period(now, timeframe)
    delta = _timedelta_for(timeframe)

    fetch_from = last_ts + delta
    if refresh_last > 0:
        fetch_from = min(fetch_from, last_closed - (refresh_last - 1) * delta)

    if fetch_from > last_closed:
        print(f"[perp-update] {symbol} {timeframe} — up to date (latest closed: {last_closed})")
        return

    # Fetch missing candles
    fetch_since_ms = int(fetch_from.timestamp() * 1000)
    print(f"[perp-update] {symbol} {timeframe} — gap from {fetch_from} to {last_closed}")
    df_missing = fetch_perp_candles(symbol, timeframe, fetch_since_ms)
    df_missing = _drop_unclosed(df_missing, timeframe, now)

    if df_missing.empty:
        print(f"[perp-update] No new closed candles for {symbol} {timeframe}")
        return

    # Fetch and store raw funding rates (separate collection).
    # Use last stored funding ts - 3d (not OHLCV fetch_since_ms): KuCoin's funding
    # history API returns 0 records silently when since >= (now - 2d).
    funding_since_ms = _get_funding_since_ms(symbol, test, fallback_ms=fetch_since_ms)
    _fetch_and_store_funding(symbol, funding_since_ms, test, tag="perp-update")

    # Load sliding window
    df_window = load_latest(symbol, timeframe, limit=SLIDING_WINDOW, test=test, market_type="perp")
    if len(df_window) < SLIDING_WINDOW:
        print(f"[perp-update] WARNING: only {len(df_window)} rows in window "
              f"(need {SLIDING_WINDOW} for full indicator accuracy)")

    # Combine and recompute
    df_full = pd.concat([df_window, df_missing])
    df_full = df_full[~df_full.index.duplicated(keep="last")]
    df_full.sort_index(inplace=True)

    df_full = compute_all(df_full, timeframe)

    # Fetch Fear & Greed once per update run
    fng = fetch_fear_greed()

    # Only upsert the newly fetched timestamps (not the window)
    valid_cols = _validatable_cols(df_full)
    new_docs = []
    for ts in df_missing.index:
        if ts not in df_full.index:
            continue
        row = df_full.loc[ts]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[-1]
        if row[valid_cols].isna().any():
            print(f"[perp-update] Skipping {ts}: NaN in indicators")
            continue
        doc = row.to_dict()
        doc["timestamp"] = ts
        new_docs.append(doc)

    new_docs = _merge_sentiment(new_docs, fng)
    n = bulk_upsert(symbol, timeframe, new_docs, test, market_type="perp")
    print(f"[perp-update] Upserted {n} new candles for {symbol} {timeframe}")


def run_perp_backfill(
    symbol: str,
    timeframe: str,
    test: bool = False,
    dry_run: bool = False,
    since: str = None,
):
    """Deep historical backfill for perpetual futures.

    Fetches max available history from KuCoin Futures, merges with existing
    data, recomputes all indicators, and upserts the full dataset. Also
    backfills funding rate history.

    Args:
        since: Optional override start date as 'YYYY-MM-DD'. If not provided,
               defaults to Jan 2020 for all timeframes (KuCoin Futures launched Aug 2019).
    """
    _sync_glossary(test)
    ensure_indexes(symbol, timeframe, test, market_type="perp")
    ensure_funding_indexes(symbol, test)

    # Determine start date — Jan 2020 default for all perp timeframes
    if since:
        since_dt = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        since_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)

    print(f"[perp-backfill] {symbol} {timeframe} (test={test}, dry_run={dry_run})")
    print(f"[perp-backfill] Fetching from {since_dt.date()} — this may take several minutes...")

    # Step 1: Fetch all candles from KuCoin Futures in paginated batches
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    delta_ms = int(_timedelta_for(timeframe).total_seconds() * 1000)
    cursor_ms = int(since_dt.timestamp() * 1000)
    all_dfs = []
    empty_streak = 0

    while cursor_ms < now_ms:
        df_batch = fetch_perp_candles(symbol, timeframe, cursor_ms, limit=1500)
        if df_batch.empty:
            # Jump forward 180 days and retry (contract may not exist at start date)
            cursor_ms += 180 * 86_400_000
            empty_streak += 1
            if empty_streak >= 20:
                break
            continue
        empty_streak = 0
        all_dfs.append(df_batch)
        last_ts_ms = int(df_batch.index.max().timestamp() * 1000)
        cursor_ms = last_ts_ms + delta_ms
        print(f"  [fetch] {len(df_batch)} candles through {df_batch.index.max().date()} "
              f"(total so far: {sum(len(d) for d in all_dfs)})")

    if not all_dfs:
        print(f"[perp-backfill] No candles returned from exchange for {symbol} {timeframe}")
        return

    df_exchange = pd.concat(all_dfs)
    df_exchange = df_exchange[~df_exchange.index.duplicated(keep="last")]
    df_exchange.sort_index(inplace=True)
    print(f"[perp-backfill] Fetched {len(df_exchange)} total candles from exchange "
          f"({df_exchange.index.min().date()} to {df_exchange.index.max().date()})")

    # Step 2: Backfill raw funding rates (separate collection)
    funding_since_ms = int(df_exchange.index.min().timestamp() * 1000)
    print(f"[perp-backfill] Fetching funding rate history...")
    _fetch_and_store_funding(symbol, funding_since_ms, test, tag="perp-backfill", limit=100_000)

    # Step 3: Load all existing data (OHLCV only)
    df_existing = load_all(symbol, timeframe, test, market_type="perp")
    if not df_existing.empty:
        print(f"[perp-backfill] Loaded {len(df_existing)} existing docs from MongoDB")
    else:
        print(f"[perp-backfill] No existing data in MongoDB")

    # Step 4: Merge — existing OHLCV wins on duplicate timestamps
    if not df_existing.empty:
        df_merged = pd.concat([df_exchange, df_existing])
        df_merged = df_merged[~df_merged.index.duplicated(keep="last")]
    else:
        df_merged = df_exchange
    df_merged.sort_index(inplace=True)
    print(f"[perp-backfill] Merged dataset: {len(df_merged)} rows")

    # Step 5: Recompute all indicators
    print(f"[perp-backfill] Computing indicators...")
    df_merged = compute_all(df_merged, timeframe)

    # Step 6: Drop NaN warmup rows (excludes all-NaN columns from short-history tokens)
    valid_cols = _validatable_cols(df_merged)
    df_clean = df_merged.dropna(subset=valid_cols)
    print(f"[perp-backfill] {len(df_clean)} rows after NaN drop "
          f"({len(df_merged) - len(df_clean)} warmup rows removed)")

    # Step 7: Build docs with FnG=None (historical)
    docs = _df_to_docs(df_clean)
    for doc in docs:
        doc["FnG_Value"] = None
        doc["FnG_Class"] = None

    if dry_run:
        print(f"[perp-backfill] DRY RUN — would upsert {len(docs)} documents. Skipping write.")
        return

    # Step 8: Upsert in chunks
    print(f"[perp-backfill] Upserting {len(docs)} documents...")
    n = bulk_upsert_chunked(symbol, timeframe, docs, test, market_type="perp")
    print(f"[perp-backfill] Done — upserted {n} documents for {symbol} {timeframe}")


# ---------------------------------------------------------------------------
# Perpetual Futures — _all variants
# ---------------------------------------------------------------------------

def run_perp_seed_all(
    timeframe: str = None,
    test: bool = False,
    count: int = SEED_WINDOW,
):
    """Run perp seed for all tokens and timeframes."""
    timeframes = [timeframe] if timeframe else list(TIMEFRAMES.keys())
    failed = []
    for sym in TOKENS:
        for tf in timeframes:
            try:
                run_perp_seed(sym, tf, test, count)
            except Exception as e:
                print(f"[perp-seed] ERROR: {sym} {tf} failed: {e}")
                failed.append(f"{sym} {tf}")
    if failed:
        print(f"\n[perp-seed] Failed: {', '.join(failed)}")


def run_perp_update_all(timeframe: str = None, test: bool = False, refresh_last: int = 0):
    """Run incremental perp update for all tokens and timeframes."""
    timeframes = [timeframe] if timeframe else list(TIMEFRAMES.keys())
    for sym in TOKENS:
        for tf in timeframes:
            try:
                run_perp_update(sym, tf, test, refresh_last=refresh_last)
            except Exception as e:
                print(f"[perp-update] ERROR: {sym} {tf} failed: {e}")


def run_perp_backfill_all(
    timeframe: str = None,
    test: bool = False,
    dry_run: bool = False,
    skip_btc: bool = False,
    since: str = None,
):
    """Run perp backfill for all tokens. Process order: 1w -> 1d -> 4h -> 1h."""
    tf_order = ["1w", "1d", "4h", "1h"]
    timeframes = [timeframe] if timeframe else tf_order
    timeframes = [tf for tf in tf_order if tf in timeframes]

    tokens = [t for t in TOKENS if not (skip_btc and t == "BTC-USDT")]

    total = len(tokens) * len(timeframes)
    done = 0
    failed = []

    for tf in timeframes:
        for sym in tokens:
            done += 1
            print(f"\n{'='*60}")
            print(f"[perp-backfill] [{done}/{total}] {sym} {tf}")
            print(f"{'='*60}")
            try:
                run_perp_backfill(sym, tf, test=test, dry_run=dry_run, since=since)
            except Exception as e:
                print(f"[perp-backfill] ERROR: {sym} {tf} failed: {e}")
                failed.append(f"{sym} {tf}")

    print(f"\n[perp-backfill] Complete: {done - len(failed)}/{total} succeeded")
    if failed:
        print(f"[perp-backfill] Failed: {', '.join(failed)}")


# ---------------------------------------------------------------------------
# Perpetual Futures — Funding rate metadata seeding
# ---------------------------------------------------------------------------

# KuCoin Futures contract symbols (native exchange format)
_KUCOIN_CONTRACT_MAP = {
    "BTC-USDT": "XBTUSDTM",
    "ETH-USDT": "ETHUSDTM",
    "SOL-USDT": "SOLUSDTM",
    "XRP-USDT": "XRPUSDTM",
    "BNB-USDT": "BNBUSDTM",
    "DOGE-USDT": "DOGEUSDTM",
    "AVAX-USDT": "AVAXUSDTM",
    "LINK-USDT": "LINKUSDTM",
    "ADA-USDT": "ADAUSDTM",
    "SUI-USDT": "SUIUSDTM",
    "DOT-USDT": "DOTUSDTM",
    "NEAR-USDT": "NEARUSDTM",
}


def seed_funding_metadata(test: bool = False):
    """Seed funding_rate_metadata collection with per-token docs."""
    from .db import upsert_funding_metadata

    for sym in TOKENS:
        contract = _KUCOIN_CONTRACT_MAP.get(sym, sym.split("-")[0].upper() + "USDTM")
        metadata = {
            "exchange": "kucoinfutures",
            "contract_symbol": contract,
            "settlement_interval_hours": 8,
            "settlements_per_day": 3,
            "settlement_times_utc": ["00:00", "08:00", "16:00"],
            "last_updated": datetime.now(timezone.utc),
        }
        upsert_funding_metadata(sym, metadata, test)
        print(f"[metadata] Seeded funding metadata for {sym} -> {contract}")
