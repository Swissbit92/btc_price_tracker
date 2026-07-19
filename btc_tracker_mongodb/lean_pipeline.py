"""Lean perp+funding ingestion for the XS research universe (no 85 indicators).

Mirrors the production perp/funding pipeline but **skips ``compute_all()``** — it stores raw
perp-daily OHLCV (Open/High/Low/Close/Volume) + funding into the standard ADR-004 collection
names (``{token}_perp_daily_price_data`` / ``{token}_funding_rate_data``), which is all CRA's
read-only ``engine/xs/`` funding-carry re-test consumes (Close + funding_rate). Reuses the
tested production fetchers/writers verbatim; the only difference from production is the absent
indicator step. Kept OUT of ``config.TOKENS`` and the production launchd jobs → zero impact on
the live 17-token carry/directional pipeline.

Parallelism: a ProcessPoolExecutor gives each worker its own ccxt + mongo singleton
(process-isolated, so the non-thread-safe ccxt sync client is safe and each process is an
independent rate-limited connection). This is I/O-bound work on a rate-limited external API —
a handful of processes is the right amount of concurrency; more would just trigger 429s.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ProcessPoolExecutor

from btc_tracker_mongodb import config, db
from btc_tracker_mongodb.extract_perp import (
    fetch_funding_rate_history,
    fetch_perp_candles,
)

logger = logging.getLogger(__name__)

# SAFETY: the lean path must NEVER write to a production token's collections — those are
# maintained (with the full 85 indicators) by the production pipeline, and a lean upsert would
# insert indicator-less bars into a live collection feeding real carry/directional signals.
PRODUCTION_SYMBOLS = {s.upper() for s in config.TOKENS}

PERP_LIMIT = 3000       # ~8yr of daily bars (exchange caps at actual history)
FUNDING_LIMIT = 6000    # ~5.5yr of 8h settlements
DAY_MS = 86_400_000

# KuCoin Futures returns [] (or a truncated partial) when `since` predates a contract's listing
# by too much — and NON-monotonically (a too-old `since` yields FEWER rows than a moderate one).
# So on a full backfill we can't use a single old floor; we try a descending window ladder and
# keep whichever `since` returns the MOST rows (= deepest history actually available per token).
# 900d comfortably covers the ~2024-04+ funded window the funding re-test uses; we don't need
# pre-2024 perp history (no funding exists there for these tokens).
ADAPTIVE_WINDOWS_D = (900, 550, 400, 270, 150, 70)


def _now_ms() -> int:
    return int(time.time() * 1000)


def perp_df_to_docs(df) -> list[dict]:
    """Convert a fetch_perp_candles DataFrame (index=timestamp, OHLCV cols) to upsert docs.
    LEAN by construction — carries only timestamp + OHLCV, never the 85 indicator columns."""
    if df is None or df.empty:
        return []
    return df.reset_index().to_dict("records")


def funding_df_to_docs(df) -> list[dict]:
    if df is None or df.empty:
        return []
    return df.reset_index().to_dict("records")


def _retry(fn, *args, tries: int = 3, base: float = 1.0, **kwargs):
    """Retry with exponential backoff — the perp/funding fetchers lack their own retry
    (unlike spot), and a 300-token backfill will hit transient 429s/timeouts."""
    last = None
    for i in range(tries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:   # noqa: BLE001 — transient network/exchange errors, then re-raise
            last = exc
            if i < tries - 1:
                time.sleep(base * (2 ** i))
    raise last


def _adaptive_backfill_fetch(symbol: str, kind: str):
    """Return the df with the MOST rows across the window ladder — robust to KuCoin's
    predates-listing quirk. `kind` is 'perp' or 'funding'."""
    best, best_n = None, -1
    for w in ADAPTIVE_WINDOWS_D:
        since = _now_ms() - w * DAY_MS
        if kind == "perp":
            df = _retry(fetch_perp_candles, symbol, "1d", since, limit=PERP_LIMIT)
        else:
            df = _retry(fetch_funding_rate_history, symbol, since_ms=since, limit=FUNDING_LIMIT)
        n = 0 if df is None or df.empty else len(df)
        if n > best_n:
            best, best_n = df, n
    return best


def lean_ingest_token(symbol: str, incremental: bool = False) -> dict:
    """Ingest one token's lean perp-daily OHLCV + funding. Idempotent (upsert by timestamp)."""
    if symbol.upper() in PRODUCTION_SYMBOLS:
        raise ValueError(
            f"refusing to lean-ingest production token {symbol} — its collections are "
            f"maintained (with indicators) by the production pipeline; lean writes are barred")
    db.ensure_indexes(symbol, "1d", market_type="perp")
    db.ensure_funding_indexes(symbol)

    if incremental:
        latest_p = db.get_latest_timestamp(symbol, "1d", market_type="perp")
        p_since = int(latest_p.timestamp() * 1000) + 1 if latest_p else _now_ms() - 900 * DAY_MS
        perp_df = _retry(fetch_perp_candles, symbol, "1d", p_since, limit=PERP_LIMIT)
        latest_f = db.get_funding_collection(symbol).find_one({}, sort=[("timestamp", -1)])
        f_since = (int(latest_f["timestamp"].timestamp() * 1000) + 1
                   if latest_f and latest_f.get("timestamp") else _now_ms() - 900 * DAY_MS)
        fund_df = _retry(fetch_funding_rate_history, symbol, since_ms=f_since, limit=FUNDING_LIMIT)
    else:
        perp_df = _adaptive_backfill_fetch(symbol, "perp")
        fund_df = _adaptive_backfill_fetch(symbol, "funding")

    perp_docs = perp_df_to_docs(perp_df)
    n_perp = db.bulk_upsert(symbol, "1d", perp_docs, market_type="perp") if perp_docs else 0
    fund_docs = funding_df_to_docs(fund_df)
    n_fund = db.bulk_upsert_funding(symbol, fund_docs) if fund_docs else 0

    return {"symbol": symbol, "perp": n_perp, "funding": n_fund}


def _ingest_worker(task: tuple) -> dict:
    symbol, incremental = task
    try:
        return lean_ingest_token(symbol, incremental=incremental)
    except Exception as exc:   # noqa: BLE001 — isolate per-token failures, keep the fleet going
        logger.warning("lean ingest failed for %s: %s", symbol, exc)
        return {"symbol": symbol, "perp": 0, "funding": 0, "error": str(exc)}


def run_lean_backfill(symbols: list[str], incremental: bool = False, workers: int = 4) -> list[dict]:
    """Ingest a list of tokens with bounded process-parallelism (per-process ccxt + mongo)."""
    tasks = [(s, incremental) for s in symbols]
    results: list[dict] = []
    if workers <= 1:
        for t in tasks:
            results.append(_ingest_worker(t))
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(_ingest_worker, tasks):
                results.append(r)
    return results
