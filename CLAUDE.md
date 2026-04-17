# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-token Crypto Price Tracker — fetches OHLCV candle data for **BTC, ETH, SOL, XRP, BNB, DOGE, AVAX, LINK, ADA, SUI, TON, DOT, NEAR, PEPE, WIF, SHIB, WLD, ARB** (18 USDT pairs) from KuCoin via CCXT, computes ~85 technical indicators + ML features, fetches the Fear & Greed Index, and stores results in local Docker MongoDB. Supports both **spot** and **perpetual futures** market types. Runs autonomously via **launchd on Mac Mini M4 Pro** (daily at 01:10 local + hourly at :05 local + watchdog at 07:00 local). GitHub Actions `workflow_dispatch` kept as manual fallback.

## Commands

```bash
# Activate the venv
source venv/bin/activate         # macOS / Linux
# source Scripts/activate        # Git Bash on Windows (legacy)

# Install dependencies
pip install -r requirements.txt

# Seed a single token (500 candle backfill)
python seed.py --symbol BTC-USDT --timeframe 1h
python seed.py --symbol BTC-USDT --timeframe 4h
python seed.py --symbol BTC-USDT --timeframe 1d

# Seed all tokens + timeframes
python seed.py --all

# Seed all timeframes for one token
python seed.py --symbol BNB-USDT --all-timeframes

# Seed from CSV (daily history)
python seed.py --symbol BTC-USDT --timeframe 1d --csv daily_history.csv

# Deep historical backfill (fetches max available history from KuCoin)
python backfill.py --symbol ETH-USDT --timeframe 1d          # single token
python backfill.py --all --timeframe 1d --skip-btc            # all altcoins, daily
python backfill.py --all --timeframe 4h                       # all tokens, 4h
python backfill.py --symbol BTC-USDT --timeframe 4h --since 2017-10-01  # custom start date
python backfill.py --all --test --dry-run                     # dry-run to test DB

# Run incremental update (single token)
python update.py --symbol BTC-USDT --timeframe 1h

# Run incremental update (all tokens, single timeframe)
python update.py --all --timeframe 1h

# Run incremental update (all tokens, all timeframes)
python update.py --all

# Use test database instead of production
python seed.py --all --test
python update.py --all --test

# Perpetual futures (add --market-type perp to any command)
python seed.py --symbol BTC-USDT --timeframe 1d --market-type perp
python seed.py --all --timeframe 1d --market-type perp --test
python update.py --all --timeframe 1h --market-type perp
python backfill.py --symbol BTC-USDT --timeframe 1d --market-type perp --test --dry-run
python backfill.py --all --timeframe 1d --market-type perp --test

# Query latest entries
python -m btc_tracker_mongodb.query --symbol BTC-USDT --timeframe 1h --limit 20

# Compare test vs production data
python -m btc_tracker_mongodb.query --symbol BTC-USDT --timeframe 1h --test --compare

# View indicator glossary from MongoDB
python -m btc_tracker_mongodb.query --glossary [--test]

# Run Flask app locally (exposes update endpoint at :8080)
python app.py

# Docker
docker build -t btc-tracker .
docker run --env-file .env btc-tracker
```

## Architecture

### Data Pipeline

All tokens share the same pipeline pattern (orchestrated by `pipeline.py`):
1. **Load** the last 200 rows from MongoDB as a sliding window
2. **Detect gaps** between the latest stored timestamp and now
3. **Fetch missing candles** from KuCoin via CCXT (`extract.py`)
4. **Append** new candles to the sliding window DataFrame
5. **Recompute all indicators** via `indicators.compute_all()` (single source of truth)
6. **Fetch Fear & Greed Index** from alternative.me API (`sentiment.py`)
7. **Bulk upsert** only newly fetched rows into MongoDB, skipping any with NaN indicators

### Deep Historical Backfill (`backfill.py`)

One-time operation to fetch max available history from KuCoin for backtesting:
1. **Determine start date** — Oct 2017 for daily (max KuCoin history), Jan 2020 for 4h/1h (or custom via `--since`)
2. **Fetch all candles** from KuCoin in paginated batches (handles partial batches and exchange data gaps)
3. **Load all existing data** from MongoDB (OHLCV only via `load_all()`)
4. **Merge** — deduplicate on timestamp, existing OHLCV wins on conflicts
5. **Recompute all indicators** on the full merged dataset
6. **Drop NaN warmup rows**, set FnG to None (historical FnG unavailable)
7. **Chunked upsert** via `bulk_upsert_chunked()` (5K-doc batches)

Safe to re-run (upsert semantics), per-token error isolation, resumable.

### MongoDB Schema

- Database: `btc_data` (production), `btc_data_test` (testing)
- **Spot collections:** `{token}_daily_price_data`, `{token}_weekly_price_data`, plus `btc_1h_price_data`
  - e.g. `btc_daily_price_data`, `eth_weekly_price_data`
  - 18 daily + 18 weekly + 18 hourly. Newer tokens (SUI/TON/WIF) have partial indicators — SMA_200/EMA_200 null until ~200 weeks of history.
- **Perp collections:** `{token}_perp_daily_price_data`, `{token}_perp_1h_price_data`
  - e.g. `btc_perp_daily_price_data`, `eth_perp_daily_price_data`
  - 18 daily + 18 hourly. KuCoin Futures doesn't support weekly candles. Perp 1h history limited to ~15 months by exchange.
- **Funding rate collections:** `{token}_funding_rate_data` (per-token, raw 8h granularity)
  - e.g. `btc_funding_rate_data`, `eth_funding_rate_data` — 18 collections
- Each document is keyed by `timestamp` (UTC datetime); unique index enforced
- `indicator_glossary` collection: indicator descriptions, categories, ranges, schema_hash. Auto-synced on every pipeline run.
- `funding_rate_glossary` collection: per-token metadata (exchange, contract symbol, settlement schedule)
- **Production timeframes:** Daily + weekly + hourly (all 18 tokens, spot + perp). 4h not in production. Infrastructure supports all timeframes — re-populate via `backfill.py` when needed.
- **Total collections:** ~110 (18 spot daily + 18 weekly + 18 spot 1h + 18 perp daily + 18 perp 1h + 18 funding + 2 metadata)

### Key Modules (`btc_tracker_mongodb/`)

| File | Purpose |
|---|---|
| `config.py` | Central config: TOKENS (18), TIMEFRAMES (4: 1h, 4h, 1d, 1w), MARKET_TYPES, PERP_SYMBOL_MAP, DB names, collection name mapping (`market_type` param) |
| `db.py` | MongoDB connection + CRUD: all functions accept `market_type="spot"` param. Funding CRUD: load_funding_rates, bulk_upsert_funding, ensure_funding_indexes, upsert_funding_metadata |
| `extract.py` | CCXT-based KuCoin **spot** data fetching: fetch_candles (with 429 retry/backoff), fetch_seed_candles |
| `extract_perp.py` | CCXT-based KuCoin **Futures** data fetching via `ccxt.kucoinfutures`: fetch_perp_candles, fetch_perp_seed_candles, fetch_funding_rate_history |
| `indicators.py` | Single source of truth for ~85 indicators + ML features: compute_all(), get_numeric_cols(), INDICATOR_GLOSSARY |
| `sentiment.py` | Fear & Greed Index fetcher: fetch_fear_greed() with graceful fallback |
| `pipeline.py` | Orchestration: spot (run_seed, run_update, run_backfill + _all) and perp (run_perp_seed, run_perp_update, run_perp_backfill + _all). All `_all` functions have per-token error isolation. Raw funding rates stored separately |
| `query.py` | Debug utility: parameterized by symbol, timeframe, test flag, with --compare and --glossary modes |

### Technical Indicators (~85 numeric + 1 string column)

Computed by `indicators.py` using `pandas-ta-classic`. Categories: Trend (SMA/EMA/Ichimoku/ADX/Supertrend/PSAR/Aroon), Momentum (RSI/StochRSI/MACD/Williams%R/CCI), Volume (OBV/CMF/MFI), Volatility (BB/Donchian/ATR/Squeeze), Risk (VaR/CVaR/Omega/Ulcer), ML Features (Z-scores/slopes/candle ratios), Sentiment (Fear & Greed).

> **Full indicator list with parameters:** [`docs/INDICATORS.md`](docs/INDICATORS.md)

When modifying indicators, only edit `indicators.py` — it is the single source of truth. Update `INDICATOR_GLOSSARY` if adding/removing columns (`get_numeric_cols()` derives from it automatically). Also update `docs/INDICATORS.md` to keep the reference in sync.

### Flask App (`app.py`)

Minimal HTTP wrapper: `GET /` triggers `run_update_all(timeframe="1h")`. Used by GCP Cloud Run + Cloud Scheduler.

### Automation (launchd on Mac Mini M4 Pro)

All times below are **local (Europe/Zurich)** — `StartCalendarInterval` in launchd plists always fires in the machine's local timezone, not UTC.

- **`com.eeva.tracker-daily`** — daily at 01:10 local via `bin/run_daily.py`:
  - Step 1: `update.py --all --timeframe 1d` (spot daily, 18 tokens)
  - Step 2: `update.py --all --timeframe 1d --market-type perp` (perp daily + funding rates)
  - Step 3: `update.py --all --timeframe 1w` (spot weekly)
  - Step 4: `export_data.py` (CSV backup to `data/`)
  - Telegram GREEN on success (with header image), RED on failure
  - Fire time offset from `:05` to `:10` to avoid colliding with hourly's `wait_for_mongo()` check on the same Docker container.
- **`com.eeva.tracker-hourly`** — every hour at :05 local via `bin/run_hourly.py`:
  - Step 1: `update.py --all --timeframe 1h` (spot, 18 tokens)
  - Step 2: `update.py --all --timeframe 1h --market-type perp` (perp, 18 tokens)
  - Telegram RED on failure only (no success notification)
- **`com.eeva.tracker-watchdog`** — daily at 07:00 local via `bin/run_watchdog.py`:
  - Independent freshness check: queries `max(timestamp)` on 72 collections (18 tokens × {1d, 1h} × {spot, perp}).
  - Thresholds: 36h for daily/perp-daily, 3h for 1h/perp-1h. Weekly is skipped (pre-existing inconsistency for some tokens).
  - Telegram RED if any collection stale (catches writer silent failures: launchd posix_spawn errors, Python crashes before notifier, Docker down, etc.).
  - Telegram GREEN heartbeat on Sundays only — absence of the weekly green = watchdog itself is broken.
  - Self-error: if the watchdog itself crashes, a RED "Watchdog Self-Error" Telegram fires with the traceback.
- **Production timeframes:** Daily + weekly + hourly (all 18 tokens, spot + perp). 4h not in production.
- **Fallback:** GitHub Actions `workflow_dispatch` (manual trigger only, writes to Atlas)
- **Logs:** Date-stamped in `logs/` (daily: 30-day retention, hourly: 14-day, watchdog: per-day).

**Known launchd pitfalls** (see memory for details):
- `StandardOutPath` / `StandardErrorPath` files with a stale `com.apple.macl` xattr cause silent `EX_CONFIG (78)` on spawn — `rm` the 0-byte file to let launchd recreate it fresh.
- `wait_for_mongo()` must be invoked **inside** the `with open(LOG_FILE)` block, not before it — otherwise silent failures leave no trace.

### Pipeline Launchers (`bin/`)

| Script | Purpose |
|--------|---------|
| `bin/run_daily.py` | Daily launcher: spot + perp + weekly + CSV export + Telegram (called by launchd) |
| `bin/run_hourly.py` | Hourly launcher: all 18 tokens 1h spot + perp, Telegram on failure only (called by launchd) |
| `bin/run_watchdog.py` | MongoDB freshness watchdog: reads 72 collections, Telegram RED on stale / GREEN heartbeat on Sundays (called by launchd) |
| `bin/btc-daily.sh` | Bash wrapper (for manual runs from terminal) |
| `bin/btc-hourly.sh` | Bash wrapper (for manual runs from terminal) |
| `bin/notify.sh` | Shared Telegram helper for bash wrappers |

**Note:** launchd plists call the Python launchers directly (not bash) to avoid macOS TCC/Full Disk Access issues. Same pattern as CRA's `com.eeva.monthly-review`.

### CSV Backup (`export_data.py`)

Exports all MongoDB collections to `data/` as CSV. Run automatically as Step 4 of daily pipeline.
```bash
python export_data.py                    # all tokens
python export_data.py --tokens BTC,ETH   # specific tokens
python export_data.py --dry-run          # preview only
```

## Environment Variables

Required in `.env`:
- `MONGODB_URI` — MongoDB connection string (`mongodb://localhost:27017` for local Docker)
- `TG_BOT_TOKEN` — Telegram bot token for failure/success alerts
- `TG_CHAT_ID` — Telegram chat ID for notifications

Note: CCXT uses KuCoin public endpoints only (no API key required).

## Important Constraints

- `backfill.py` fetches deep history; default start dates are Oct 2017 (daily) and Jan 2020 (4h/1h). Override with `--since YYYY-MM-DD`.
- Update scripts require **at least 200 rows** already in MongoDB to compute long-window indicators (SMA_200, EMA_200). Always run `seed.py` first.
- `pandas-ta-classic` is the TA library (not `pandas-ta` or `ta`). Import as `import pandas_ta_classic as ta`.
- Fibonacci column names use underscores not dots: `Fib_236`, `Fib_382`, `Fib_500`, `Fib_618`, `Fib_100` (MongoDB rejects dots in field names).
- StochRSI values are normalized to [0, 1] range (not [0, 100]).
- `ccxt` is pinned to `4.5.40` in `requirements.txt` (v4.5.41 has a packaging bug). Bump the pin when a fixed release is available.
- CCXT handles KuCoin rate limiting automatically (`enableRateLimit: True`). Additionally, `fetch_candles()` in `extract.py` retries up to 3 times with exponential backoff on 429 errors (CCXT misclassifies KuCoin's `429000` as `ExchangeError`, not `RateLimitExceeded`).
- Python version: 3.12 locally (venv). CI uses 3.11 (GH Actions fallback).
- Fear & Greed API is free, no signup: `https://api.alternative.me/fng/`. Graceful fallback if unreachable.
- VWAP: rolling 24-bar for intraday (1h, 4h), cumulative for daily and weekly.
- `compute_all()` takes a `timeframe` parameter ("1h", "4h", "1d", "1w") that affects VWAP calculation.
- Migration status tracked in `docs/MIGRATION.md`.

## MCP Server (`mcp_server.py`)

Read-only MCP server that exposes MongoDB data to Claude Code via 7 tools. Registered in `.mcp.json` — auto-discovered when Claude Code opens the project.

### Tools

| Tool | Purpose |
|------|---------|
| `list_collections()` | List all collections: spot + perp + weekly + funding (no DB call) |
| `query_price_data(symbol, timeframe, limit, fields, market_type)` | Latest N docs, optional field filtering. `market_type="spot"` or `"perp"` |
| `get_latest_price(symbol, timeframe, market_type)` | Single most recent document |
| `get_indicator_glossary()` | Fetch indicator glossary from metadata collection |
| `get_collection_stats(symbol, timeframe, market_type)` | Doc count, date range, column list |
| `query_by_date_range(symbol, start_date, end_date, timeframe, fields, limit, market_type)` | Query within a date range (chronological) |
| `query_funding_rates(symbol, limit, start_date, end_date)` | Query 8h funding rate history from `{token}_funding_rate_data` |

All tools accept flexible symbol input (`"BTC"`, `"btc"`, or `"BTC-USDT"`) and return JSON. Errors are returned as `{"error": "message"}` so Claude can reason about failures. Tools with `market_type` default to `"spot"` for backward compatibility.

### Dependencies

- `mcp` (Python MCP SDK) — added to `requirements.txt`
- Reuses `get_collection()`, `get_db()` from `db.py` and config constants
