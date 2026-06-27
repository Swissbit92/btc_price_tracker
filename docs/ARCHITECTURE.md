---
title: Architecture (btc_price_tracker)
status: active
created: 2026-04-19
last_reviewed_on: 2026-05-30
review_in: 6 months
applies_to: btc_price_tracker
---

# Architecture

## Data Pipeline

All tokens share the same pipeline pattern (orchestrated by `pipeline.py`):
1. **Load** the last 200 rows from MongoDB as a sliding window
2. **Detect gaps** between the latest stored timestamp and now
3. **Fetch missing candles** from KuCoin via CCXT (`extract.py`)
4. **Append** new candles to the sliding window DataFrame
5. **Recompute all indicators** via `indicators.compute_all()` (single source of truth)
6. **Fetch Fear & Greed Index** from alternative.me API (`sentiment.py`)
7. **Bulk upsert** only newly fetched rows into MongoDB, skipping any with NaN indicators

## Deep Historical Backfill (`backfill.py`)

One-time operation to fetch max available history from KuCoin:
1. **Determine start date** — Oct 2017 for daily, Jan 2020 for 4h/1h (override via `--since`)
2. **Fetch all candles** from KuCoin in paginated batches
3. **Load existing data** from MongoDB (OHLCV only via `load_all()`)
4. **Merge** — deduplicate on timestamp, existing OHLCV wins on conflicts
5. **Recompute all indicators** on the full merged dataset
6. **Drop NaN warmup rows**, set FnG to None
7. **Chunked upsert** via `bulk_upsert_chunked()` (5K-doc batches)

Safe to re-run (upsert semantics), per-token error isolation, resumable.

## MongoDB Schema

- Database: `btc_data` (production), `btc_data_test` (testing)
- **Spot:** `{token}_daily_price_data`, `{token}_weekly_price_data`, `{token}_1h_price_data` — 17 each. Newer tokens (SUI/WIF) have partial indicators (SMA_200/EMA_200 null until ~200 weeks history).
- **Perp:** `{token}_perp_daily_price_data`, `{token}_perp_1h_price_data` — 18 each. No weekly (KuCoin Futures limitation). Perp 1h limited to ~15 months by exchange.
- **Funding:** `{token}_funding_rate_data` — 17 collections, raw 8h granularity.
- Each document keyed by `timestamp` (UTC); unique index enforced.
- `indicator_glossary` collection: auto-synced every pipeline run.
- `funding_rate_glossary`: per-token metadata (exchange, contract symbol, settlement schedule).
- **Production timeframes:** daily + weekly + hourly (17 tokens, spot + perp). 4h not in production.
- **Total:** ~110 collections.

Ecosystem collection naming contract: [../docs/shared/mongodb_contract.md](../docs/shared/mongodb_contract.md)

## Key Modules (`btc_tracker_mongodb/`)

| File | Purpose |
|---|---|
| `config.py` | TOKENS (18), TIMEFRAMES, MARKET_TYPES, PERP_SYMBOL_MAP, DB names, collection name mapping |
| `db.py` | MongoDB CRUD. All functions accept `market_type="spot"` param. Full funding CRUD. |
| `extract.py` | KuCoin **spot** CCXT: `fetch_candles` (429 retry/backoff), `fetch_seed_candles` |
| `extract_perp.py` | KuCoin **Futures** via `ccxt.kucoinfutures`: perp candles, funding rate history |
| `indicators.py` | Single source of truth for ~85 indicators: `compute_all()`, `INDICATOR_GLOSSARY` |
| `sentiment.py` | Fear & Greed Index fetcher with graceful fallback |
| `pipeline.py` | Orchestration: spot + perp seed/update/backfill `_all` variants. Per-token error isolation. |
| `query.py` | Debug: symbol/timeframe/test flags, `--compare`, `--glossary` modes |

## Technical Indicators (~85)

Computed by `indicators.py` using `pandas-ta-classic`. Categories: Trend (SMA/EMA/Ichimoku/ADX/Supertrend/PSAR/Aroon), Momentum (RSI/StochRSI/MACD/Williams%R/CCI), Volume (OBV/CMF/MFI), Volatility (BB/Donchian/ATR/Squeeze), Risk (VaR/CVaR/Omega/Ulcer), ML Features (Z-scores/slopes/candle ratios), Sentiment (Fear & Greed).

Full list: [docs/INDICATORS.md](INDICATORS.md).

**Change protocol:** only edit `indicators.py`. Update `INDICATOR_GLOSSARY` for any column add/remove. Column names are a **public API** — coordinate with CRA before any rename (ADR-001).

## Pipeline Launchers (`bin/`)

| Script | Purpose |
|--------|---------|
| `bin/run_daily.py` | spot + perp + weekly + CSV export + Telegram GREEN/RED |
| `bin/run_hourly.py` | 17 tokens 1h spot + perp, Telegram RED on failure only |
| `bin/run_watchdog.py` | Freshness check of 85 collections (68 OHLCV + 17 funding_rate), Telegram RED on stale / GREEN Sundays |
| `bin/btc-daily.sh` | Bash wrapper for manual terminal runs |
| `bin/btc-hourly.sh` | Bash wrapper for manual terminal runs |
| `bin/notify.sh` | Shared Telegram helper |

launchd plists call Python launchers directly — macOS TCC blocks bash.

## Flask App (`app.py`)

`GET /` triggers `run_update_all(timeframe="1h")`. Kept for legacy Docker testing; primary automation is launchd on Mac Mini.

## Known API Quirks

### KuCoin funding rate history — ~2-day dead zone

`fetch_funding_rate_history(since=T)` returns 0 records silently when `T >= (now − 2d)`. This is a KuCoin API behaviour, not a CCXT bug.

**Impact:** any incremental update that derives `since_ms` from a recent gap (e.g. yesterday's OHLCV date) will get 0 records and log nothing — invisible failure.

**Mitigation (implemented 2026-04-26):** `_get_funding_since_ms()` always starts 3 days behind the last stored funding timestamp. The 3-day window is outside the dead zone. Upsert idempotency handles the overlap. See `pipeline.py:_get_funding_since_ms`.

**Do not** replace this with a fixed lookback offset from `now` — the offset must be anchored to the last stored MongoDB timestamp to avoid re-fetching unbounded history on every run.

## CSV Backup (`export_data.py`)

```bash
python export_data.py                    # all tokens (auto Step 4 of daily pipeline)
python export_data.py --tokens BTC,ETH
python export_data.py --dry-run
```
