# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-token Crypto Price Tracker — fetches OHLCV candle data for **BTC, ETH, SOL, XRP, BNB** (USDT pairs) from KuCoin via CCXT, computes ~79 technical indicators + ML features, fetches the Fear & Greed Index, and stores results in MongoDB Atlas. Runs autonomously via GitHub Actions (hourly, 4-hourly, and daily cron jobs) or optionally via GCP Cloud Run.

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

# Run incremental update (single token)
python update.py --symbol BTC-USDT --timeframe 1h

# Run incremental update (all tokens, single timeframe)
python update.py --all --timeframe 1h

# Run incremental update (all tokens, all timeframes)
python update.py --all

# Use test database instead of production
python seed.py --all --test
python update.py --all --test

# Query latest entries
python -m btc_tracker_mongodb.query --symbol BTC-USDT --timeframe 1h --limit 20

# Compare test vs production data
python -m btc_tracker_mongodb.query --symbol BTC-USDT --timeframe 1h --test --compare

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

### MongoDB Schema

- Database: `btc_data` (production), `btc_data_test` (testing)
- Collection naming: `{token}_1h_price_data`, `{token}_4h_price_data`, `{token}_daily_price_data`
  - e.g. `btc_1h_price_data`, `eth_4h_price_data`, `sol_daily_price_data`, `bnb_1h_price_data`
- Each document is keyed by `timestamp` (UTC datetime); unique index enforced
- 5 tokens x 3 timeframes = 15 collections total

### Key Modules (`btc_tracker_mongodb/`)

| File | Purpose |
|---|---|
| `config.py` | Central config: TOKENS (5), TIMEFRAMES (3), DB names, collection name mapping |
| `db.py` | MongoDB connection + CRUD: get_db, get_collection, load_latest, bulk_upsert, ensure_indexes |
| `extract.py` | CCXT-based KuCoin data fetching: fetch_candles, fetch_seed_candles |
| `indicators.py` | Single source of truth for ~79 indicators + ML features: compute_all(), get_numeric_cols() |
| `sentiment.py` | Fear & Greed Index fetcher: fetch_fear_greed() with graceful fallback |
| `pipeline.py` | Orchestration: run_seed, run_update, run_seed_from_csv, run_seed_all, run_update_all |
| `query.py` | Debug utility: parameterized by symbol, timeframe, test flag, with --compare mode |

### Technical Indicators (~79 numeric + 1 string column)

Computed by `indicators.py` using `pandas-ta-classic`:

**Trend:** SMA (50, 100, 200), EMA (20, 50, 100, 200), Ichimoku (9, 26, 52), ADX / +DI / -DI (14), Supertrend (7, 3.0), KAMA (10), HMA (20), PSAR, Aroon (Up/Down/Osc, 25)
**Momentum:** RSI (14), Stochastic RSI (14, K=3, D=3), Stochastic (K=14, D=3), MACD (12, 26, 9), Williams %R (14), CCI (20), TRIX (18)
**Volume:** OBV, CMF (20), MFI (14)
**Volatility:** Bollinger Bands (20, 2sigma), BB Width, Donchian Channel (20), ATR (14), NATR (14), Parkinson Vol (14), Realized Vol (14, 30), Vol Ratio (14/30), Choppiness Index (14), Squeeze Momentum (flag + momentum)
**Price levels:** Fibonacci retracement (rolling 50-period), VWAP (rolling 24-bar for intraday, cumulative for daily)
**Custom:** HDPR (mean-reversion, SMA_50 reuse, 3% threshold)
**ML Features:** Z-scores (Close/RSI/Volume, 100-period), Candle body/wick ratios (ATR-normalized), Price vs EMA20/SMA200 (ATR-normalized), RSI slope (3), MACD slope (3)
**Derived:** Log returns (1, 4, 12, 24 periods), temporal features (hour/dow sin/cos)
**Sentiment:** Fear & Greed Index (FnG_Value: 0-100 int, FnG_Class: string)

When modifying indicators, only edit `indicators.py` — it is the single source of truth. Update `get_numeric_cols()` if adding/removing columns. Also update the glossary at [`docs/INDICATORS.md`](docs/INDICATORS.md) to keep the reference in sync.

### Flask App (`app.py`)

Minimal HTTP wrapper: `GET /` triggers `update_hourly.main()`. Used by GCP Cloud Run + Cloud Scheduler. Will be updated to use new pipeline in cleanup phase.

### Automation

- `.github/workflows/update-hourly.yml` — cron `0 * * * *` runs `python update.py --all --timeframe 1h`
- `.github/workflows/update-4h.yml` — cron `0 */4 * * *` runs `python update.py --all --timeframe 4h`
- `.github/workflows/update-daily.yml` — cron `5 1 * * *` runs `python update.py --all --timeframe 1d`
- Secret required in GitHub Actions: `MONGODB_URI`

## Environment Variables

Required in `.env` for local development:
- `MONGODB_URI` — MongoDB Atlas connection string

Note: CCXT uses KuCoin public endpoints only (no API key required). Legacy env vars (`KUCOIN_API_KEY`, etc.) are no longer needed by the new pipeline.

## Important Constraints

- Update scripts require **at least 200 rows** already in MongoDB to compute long-window indicators (SMA_200, EMA_200). Always run `seed.py` first.
- `pandas-ta-classic` is the TA library (not `pandas-ta` or `ta`). Import as `import pandas_ta_classic as ta`.
- Fibonacci column names use underscores not dots: `Fib_236`, `Fib_382`, `Fib_500`, `Fib_618`, `Fib_100` (MongoDB rejects dots in field names).
- StochRSI values are normalized to [0, 1] range (not [0, 100]).
- CCXT handles KuCoin rate limiting automatically (`enableRateLimit: True`).
- Python version: 3.11 locally (venv) and in CI.
- Fear & Greed API is free, no signup: `https://api.alternative.me/fng/`. Graceful fallback if unreachable.
- VWAP: rolling 24-bar for intraday (1h, 4h), cumulative for daily.
- `compute_all()` takes a `timeframe` parameter ("1h", "4h", "1d") that affects VWAP calculation.
- Migration status tracked in `docs/MIGRATION.md`.
