# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-token Crypto Price Tracker — fetches OHLCV candle data for **BTC, ETH, SOL, XRP, BNB, DOGE, AVAX, LINK, ADA, SUI, TON, DOT, NEAR** (13 USDT pairs) from KuCoin via CCXT, computes ~85 technical indicators + ML features, fetches the Fear & Greed Index, and stores results in MongoDB Atlas. Supports both **spot** and **perpetual futures** market types. Runs autonomously via GitHub Actions (hourly, 4-hourly, and daily cron jobs) or optionally via GCP Cloud Run.

## Commands

```bash
# Activate the venv (repo root IS the venv)
source Scripts/activate          # Git Bash on Windows
.\Scripts\Activate.ps1           # PowerShell

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
- Collection naming: `{token}_1h_price_data`, `{token}_4h_price_data`, `{token}_daily_price_data`
  - e.g. `btc_1h_price_data`, `eth_4h_price_data`, `sol_daily_price_data`, `doge_1h_price_data`
- Each document is keyed by `timestamp` (UTC datetime); unique index enforced
- 13 tokens x 3 timeframes = 39 spot collections total
- **Perpetual futures collections:** `{token}_perp_1h_price_data`, `{token}_perp_4h_price_data`, `{token}_perp_daily_price_data`
  - e.g. `btc_perp_1h_price_data`, `eth_perp_4h_price_data`, `sol_perp_daily_price_data`
  - 13 tokens x 3 timeframes = 39 perp collections
- **Funding rate collections:** `{token}_funding_rate_data` (per-token, 8h granularity)
  - e.g. `btc_funding_rate_data`, `eth_funding_rate_data` — 13 collections
- `funding_rate_metadata` collection: per-token metadata (exchange, contract symbol, settlement schedule)
- `indicator_metadata` collection: stores a single `indicator_glossary` document with column descriptions, categories, ranges, and a `schema_hash` for change detection. Auto-synced on every pipeline run.

### Key Modules (`btc_tracker_mongodb/`)

| File | Purpose |
|---|---|
| `config.py` | Central config: TOKENS (13), TIMEFRAMES (3), MARKET_TYPES, PERP_SYMBOL_MAP, DB names, collection name mapping (`market_type` param) |
| `db.py` | MongoDB connection + CRUD: all functions accept `market_type="spot"` param. Funding CRUD: load_funding_rates, bulk_upsert_funding, ensure_funding_indexes, upsert_funding_metadata |
| `extract.py` | CCXT-based KuCoin **spot** data fetching: fetch_candles, fetch_seed_candles |
| `extract_perp.py` | CCXT-based KuCoin **Futures** data fetching via `ccxt.kucoinfutures`: fetch_perp_candles, fetch_perp_seed_candles, fetch_funding_rate_history |
| `indicators.py` | Single source of truth for ~85 indicators + ML features + 3 derivatives columns: compute_all(), get_numeric_cols(), INDICATOR_GLOSSARY |
| `sentiment.py` | Fear & Greed Index fetcher: fetch_fear_greed() with graceful fallback |
| `pipeline.py` | Orchestration: spot (run_seed, run_update, run_backfill + _all) and perp (run_perp_seed, run_perp_update, run_perp_backfill + _all). Funding alignment via _align_funding_to_candles() |
| `query.py` | Debug utility: parameterized by symbol, timeframe, test flag, with --compare and --glossary modes |

### Technical Indicators (~85 numeric + 1 string column)

Computed by `indicators.py` using `pandas-ta-classic`:

**Trend:** SMA (50, 100, 200), EMA (20, 50, 100, 200), Ichimoku (9, 26, 52), ADX / +DI / -DI (14), Supertrend (7, 3.0), KAMA (10), HMA (20), PSAR, Aroon (Up/Down/Osc, 25)
**Momentum:** RSI (14), Stochastic RSI (14, K=3, D=3), Stochastic (K=14, D=3), MACD (12, 26, 9), Williams %R (14), CCI (20), TRIX (18)
**Volume:** OBV, CMF (20), MFI (14)
**Volatility:** Bollinger Bands (20, 2sigma), BB Width, Donchian Channel (20), ATR (14), NATR (14), Parkinson Vol (14), Realized Vol (14, 30), Vol Ratio (14/30), Choppiness Index (14), Squeeze Momentum (flag + momentum)
**Risk:** VaR (5th percentile, 50-period), CVaR (50-period), Omega Ratio (50-period), Tail Ratio (50-period), Ulcer Index (14-period), Kappa Ratio (order 3, 50-period)
**Price levels:** Fibonacci retracement (rolling 50-period), VWAP (rolling 24-bar for intraday, cumulative for daily)
**Custom:** HDPR (mean-reversion, SMA_50 reuse, 3% threshold)
**ML Features:** Z-scores (Close/RSI/Volume, 100-period), Candle body/wick ratios (ATR-normalized), Price vs EMA20/SMA200 (ATR-normalized), RSI slope (3), MACD slope (3)
**Derived:** Log returns (1, 4, 12, 24 periods), temporal features (hour/dow sin/cos)
**Sentiment:** Fear & Greed Index (FnG_Value: 0-100 int, FnG_Class: string)
**Derivatives (perp collections only):** Funding_Rate (aggregated per candle period), Mark_Price (at closest settlement), Basis_Pct ((mark-index)/index*100). These are pipeline-injected, not computed by `compute_all()`. Excluded from NaN validation.

When modifying indicators, only edit `indicators.py` — it is the single source of truth. Update `INDICATOR_GLOSSARY` if adding/removing columns (`get_numeric_cols()` derives from it automatically). Also update the glossary at [`docs/INDICATORS.md`](docs/INDICATORS.md) to keep the human-readable reference in sync.

### Flask App (`app.py`)

Minimal HTTP wrapper: `GET /` triggers `run_update_all(timeframe="1h")`. Used by GCP Cloud Run + Cloud Scheduler.

### Automation

- `.github/workflows/update-hourly.yml` — cron `0 * * * *` runs spot + perp updates for 1h
- `.github/workflows/update-4h.yml` — cron `0 */4 * * *` runs spot + perp updates for 4h
- `.github/workflows/update-daily.yml` — cron `5 1 * * *` runs spot + perp updates for 1d
- Each workflow runs spot first, then perp (sequential steps, shared MONGODB_URI secret)
- Secret required in GitHub Actions: `MONGODB_URI`

## Environment Variables

Required in `.env` for local development:
- `MONGODB_URI` — MongoDB Atlas connection string

Note: CCXT uses KuCoin public endpoints only (no API key required). Legacy env vars (`KUCOIN_API_KEY`, etc.) are no longer needed by the new pipeline.

## Important Constraints

- `backfill.py` fetches deep history; default start dates are Oct 2017 (daily) and Jan 2020 (4h/1h). Override with `--since YYYY-MM-DD`.
- Update scripts require **at least 200 rows** already in MongoDB to compute long-window indicators (SMA_200, EMA_200). Always run `seed.py` first.
- `pandas-ta-classic` is the TA library (not `pandas-ta` or `ta`). Import as `import pandas_ta_classic as ta`.
- Fibonacci column names use underscores not dots: `Fib_236`, `Fib_382`, `Fib_500`, `Fib_618`, `Fib_100` (MongoDB rejects dots in field names).
- StochRSI values are normalized to [0, 1] range (not [0, 100]).
- `ccxt` is pinned to `4.5.40` in `requirements.txt` (v4.5.41 has a packaging bug). Bump the pin when a fixed release is available.
- CCXT handles KuCoin rate limiting automatically (`enableRateLimit: True`).
- Python version: 3.11 locally (venv) and in CI.
- Fear & Greed API is free, no signup: `https://api.alternative.me/fng/`. Graceful fallback if unreachable.
- VWAP: rolling 24-bar for intraday (1h, 4h), cumulative for daily.
- `compute_all()` takes a `timeframe` parameter ("1h", "4h", "1d") that affects VWAP calculation.
- Migration status tracked in `docs/MIGRATION.md`.

## MCP Server (`mcp_server.py`)

Read-only MCP server that exposes MongoDB data to Claude Code via 7 tools. Registered in `.mcp.json` — auto-discovered when Claude Code opens the project.

### Tools

| Tool | Purpose |
|------|---------|
| `list_collections()` | List all 91 collections: 39 spot + 39 perp + 13 funding (no DB call) |
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
