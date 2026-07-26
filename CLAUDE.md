# CLAUDE.md

Multi-token OHLCV pipeline — 17 tokens (BTC/ETH/SOL/XRP/BNB/DOGE/AVAX/LINK/ADA/SUI/DOT/NEAR/PEPE/WIF/SHIB/WLD/ARB), ~85 indicators, spot + perp + funding, local Docker MongoDB. Runs via launchd on Mac Mini (daily **03:10** · hourly :05 · watchdog 07:00, all local Europe/Zurich). Daily moved 01:10 → 03:10 on 2026-07-19: launchd fires on *machine local* time, so 01:10 was 00:10 UTC under CET but **23:10 UTC under CEST** — the wrong side of the UTC day boundary for half the year. Any local hour 02:10-22:00 is past the boundary in both regimes.

**Lean XS research universe (2026-07-10, separate from the 17 production tokens):** an additive, disk-cheap path that ingests a curated ~283-token liquid-perp set (top-300 by 24h volume minus the 17 production tokens) with **perp-daily OHLCV + funding ONLY — no 85 indicators** (`compute_all()` skipped), to feed CRA's read-only `engine/xs/` cross-sectional funding re-test on a wide universe. Kept OUT of `config.TOKENS` and the production launchd jobs (zero impact on the live carry/directional pipeline); a hard guard refuses lean writes to production-token collections. Total added: **~52 MB** (lean = tiny) across ~566 collections. Commands: `python tools/xs/select_xs_universe.py --top-n 300` (rank+write `config/xs_universe.json`) → `python tools/xs/lean_ingest.py [--incremental] [--workers 4]` (backfill / refresh). Optional separate refresh: `deploy/com.eeva.xs-refresh.plist` (provided, NOT auto-installed). **Re-test outcome (2026-07-10):** funding-carry XS = 🔴 RED on the 300-token universe (55/40/57th pctile vs random-rank across splits) — the earlier 12-token GREEN was a thin-cross-section artifact; the expansion did its job (ruled it out cheaply). See CRA `docs/XS_ROUND_A_CROSS_SECTIONAL_2026-07-10.md`.

**⚠️ Only CLOSED candles are written (since 2026-07-19).** `run_update` bounds its fetch window by `_last_closed_period()` and filters the fetched frame — previously it stored the *currently forming* candle and the gap check skipped it forever, so **76% of daily Closes since the 2026-03-29 DST change were wrong** (and 1h bars held ~5 minutes of trading). `--refresh-last N` re-fetches the most recent N closed candles so revisions and hand-over rows self-heal; wired as `2` into both `bin/run_daily.py` and `bin/run_hourly.py`. `run_hourly` also closes the daily/weekly bars, so **correctness no longer depends on the launchd schedule** (near-free: `run_update` returns before fetching unless a period closed). **Pre-2026-07-19 history is still truncated** — open R10 repair decision in [docs/ROADMAP.md](docs/ROADMAP.md); note `backfill.py` CANNOT repair it (its merge keeps existing rows on a collision).

**Ecosystem context:** [../CLAUDE.md](../CLAUDE.md) · launchd schedule & gotchas: [../docs/shared/launchd_schedule.md](../docs/shared/launchd_schedule.md)

## Commands

```bash
source venv/bin/activate
pip install -r requirements.txt

# Incremental updates (production use)
python update.py --all                          # all tokens, all timeframes
python update.py --all --timeframe 1h
python update.py --all --timeframe 1h --market-type perp

# Seed (first time or after wipe)
python seed.py --all
python seed.py --symbol BTC-USDT --timeframe 1d

# Deep historical backfill
python backfill.py --all --timeframe 1d
python backfill.py --symbol BTC-USDT --timeframe 4h --since 2017-10-01

# Query / debug
python -m btc_tracker_mongodb.query --symbol BTC-USDT --timeframe 1h --limit 20
python -m btc_tracker_mongodb.query --glossary

# CSV backup
python export_data.py                           # auto Step 4 of daily pipeline

# Docker
docker build -t btc-tracker . && docker run --env-file .env btc-tracker
```

## Architecture

Pipeline design, MongoDB schema, module map, indicator list, launcher scripts: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## launchd jobs (this repo)

- **`com.eeva.tracker-daily`** (03:10 local) → `bin/run_daily.py`: spot-daily + perp-daily + weekly + CSV export. Telegram GREEN/RED. Offset to :10 to avoid hourly `wait_for_mongo()` collision.
- **`com.eeva.tracker-hourly`** (:05 every hour) → `bin/run_hourly.py`: 17 tokens 1h spot + perp. RED on failure only.
- **`com.eeva.tracker-watchdog`** (07:00 local) → `bin/run_watchdog.py`: freshness check of 85 collections (68 OHLCV + 17 funding_rate). Thresholds: 36h daily, 3h hourly. RED on stale; GREEN heartbeat Sundays.
- **Fallback:** GitHub Actions `workflow_dispatch` (manual; writes to Atlas).
- **Logs:** `logs/` date-stamped (daily: 30-day, hourly: 14-day, watchdog: per-day).

Pitfall: `wait_for_mongo()` must be called **inside** the `with open(LOG_FILE)` block — outside causes silent failures with no log trace.

## Environment variables

Required in `.env`: `MONGODB_URI`, `TG_BOT_TOKEN`, `TG_CHAT_ID`. CCXT uses KuCoin public endpoints (no API key).

## Non-obvious constraints

- Update scripts require **≥200 rows** in MongoDB before running (SMA_200/EMA_200 warmup). Always `seed.py` first on a fresh DB.
- `pandas-ta-classic` only (not `pandas-ta` or `ta`). Import: `import pandas_ta_classic as ta`.
- Fibonacci columns use underscores: `Fib_236`, `Fib_382` — MongoDB rejects dots in field names.
- StochRSI normalized to [0, 1] (not [0, 100]).
- `ccxt` pinned to `4.5.40` — v4.5.41 has a packaging bug.
- `fetch_candles()` retries 3× with exponential backoff on 429 — CCXT misclassifies KuCoin's `429000` as `ExchangeError`.
- VWAP: rolling 24-bar for intraday (1h, 4h), cumulative for daily/weekly.

## MCP Server (`mcp_server.py`)

Read-only, registered in `.mcp.json`. 7 tools: `list_collections`, `query_price_data`, `get_latest_price`, `get_indicator_glossary`, `get_collection_stats`, `query_by_date_range`, `query_funding_rates`. All accept `"BTC"`, `"btc"`, or `"BTC-USDT"`. All return JSON; errors as `{"error": "..."}`.
