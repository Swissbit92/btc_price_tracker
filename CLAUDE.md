# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bitcoin Cloud Price Tracker — fetches BTC/USDT candle data from the KuCoin public API, computes technical indicators, and stores results in MongoDB Atlas. Runs autonomously via GitHub Actions (hourly and daily cron jobs) or optionally via GCP Cloud Run.

## Commands

```bash
# Activate the venv (repo root IS the venv)
source Scripts/activate          # Git Bash on Windows
.\Scripts\Activate.ps1           # PowerShell

# Install dependencies
pip install -r requirements.txt

# Seed hourly data (500h backfill into MongoDB)
python btc_tracker_mongodb/seed_historical.py

# Seed daily data (from daily_history.csv into MongoDB)
python btc_tracker_mongodb/seed_daily.py

# Run hourly update manually
python btc_tracker_mongodb/update_hourly.py

# Run daily update manually
python btc_tracker_mongodb/update_daily.py

# Query latest hourly entries
python btc_tracker_mongodb/mongodb_query.py

# Query latest daily entries
python btc_tracker_mongodb/query_latest_daily.py

# Run Flask app locally (exposes update endpoint at :8080)
python app.py

# Docker
docker build -t btc-tracker .
docker run --env-file .env btc-tracker
```

## Architecture

### Data Pipeline

Two parallel pipelines (hourly and daily) share an identical pattern:
1. **Load** the last 200 rows from MongoDB as a sliding window
2. **Detect gaps** between the latest stored timestamp and now
3. **Fetch missing candles** from KuCoin public API (`/api/v1/market/candles`)
4. **Append** new candles to the sliding window DataFrame
5. **Recompute all indicators** on the combined DataFrame (requires 200+ rows)
6. **Upsert** only newly fetched rows into MongoDB, skipping any with NaN indicators

### MongoDB Schema

- Database: `btc_data`
- Collection `1h_price_data` — hourly candles + indicators (used by `update_hourly.py`, `seed_historical.py`)
- Collection `daily_price_data` — daily candles + indicators (used by `update_daily.py`, `seed_daily.py`)
- Each document is keyed by `timestamp` (UTC datetime); upserts use `{"timestamp": ts}` as filter

### Key Modules (`btc_tracker_mongodb/`)

| File | Purpose |
|---|---|
| `seed_historical.py` | One-time backfill: fetches 500 hourly candles from KuCoin API |
| `seed_daily.py` | One-time backfill: reads `daily_history.csv` (BTC-USD since 2016) |
| `update_hourly.py` | Incremental hourly updater with gap detection (main entry point) |
| `update_daily.py` | Incremental daily updater with gap detection |
| `mongodb_query.py` | Debug utility: prints latest 10 hourly documents |
| `query_latest_daily.py` | Debug utility: prints latest 100 hourly documents |

### Technical Indicators Computed

All scripts compute the same indicator suite on the OHLCV DataFrame:
- SMA (50, 100, 200), EMA (20, 50, 100, 200)
- RSI (14), Stochastic RSI (14, K=3, D=3)
- Bollinger Bands (20, 2σ), Donchian Channel (20)
- Ichimoku Cloud (9, 26, 52)
- MACD (12, 26, 9)
- Fibonacci retracement levels (0.236, 0.382, 0.5, 0.618, 1.0)
- Moon cycle phase (via `skyfield` + `de421.bsp` ephemeris file)
- HDPR (High Distance Price Reversal) — custom mean-reversion signal (MA50, 3% threshold)

Indicator computation logic is duplicated across the four scripts. When adding or modifying an indicator, update it in all four: `seed_historical.py`, `seed_daily.py`, `update_hourly.py`, `update_daily.py`. Also update the `numeric_cols` list used for NaN validation.

### Flask App (`app.py`)

Minimal HTTP wrapper: `GET /` triggers `update_hourly.main()`. Used by GCP Cloud Run + Cloud Scheduler as an alternative to GitHub Actions.

### Automation

- `.github/workflows/update-hourly.yml` — cron `0 * * * *` runs `update_hourly.py`
- `.github/workflows/update-daily.yml` — cron `5 1 * * *` runs `update_daily.py`
- Secrets required in GitHub Actions: `MONGODB_URI`, `KUCOIN_API_KEY`, `KUCOIN_API_SECRET`

## Environment Variables

Required in `.env` for local development:
- `MONGODB_URI` — MongoDB Atlas connection string
- `KUCOIN_API_KEY`, `KUCOIN_API_SECRET`, `KUCOIN_PASSPHRASSE` — main account (used by seed scripts)
- `KUCOIN_USERNAME_SUB1`, `KUCOIN_API_KEY_SUB1`, `KUCOIN_API_SECRET_SUB1`, `KUCOIN_API_PASSPHRASE_SUB1` — sub-account (used by update scripts)

Note: The public market data endpoints don't require API auth, but the credentials are loaded for potential future private endpoint use.

## Important Constraints

- Update scripts require **at least 200 rows** already in MongoDB to compute long-window indicators (SMA_200, EMA_200). Always run the corresponding seed script first.
- The `de421.bsp` ephemeris file (16 MB) in the repo root is required by `skyfield` for moon phase calculation. Do not delete it.
- KuCoin API rate limit is ~300 requests/min. For large backfills, add `time.sleep(1)` between calls.
- Python version: 3.11 locally (venv), 3.10 in CI and Docker.
