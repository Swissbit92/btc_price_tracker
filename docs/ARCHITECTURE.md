---
title: Architecture (btc_price_tracker)
status: active
created: 2026-04-19
last_reviewed_on: 2026-05-30
review_in: 6 months
applies_to: btc_price_tracker
published_url: https://claude.ai/code/artifact/64858b08-77c5-4a12-92d9-43988e8c6a5a
---

# Architecture

## Topology

```archview
{
  "caption": "Three launchd jobs, one shared pipeline, and the collections every downstream repo reads.",
  "nodes": [
    {"id":"launchd","label":"launchd","sub":"daily 03:10 · hourly :05 · watchdog 07:00","tech":"plist · local time","kind":"external"},
    {"id":"daily","label":"bin/run_daily.py","sub":"spot + perp + weekly + CSV","tech":"Python 3.12","kind":"service"},
    {"id":"hourly","label":"bin/run_hourly.py","sub":"17 tokens 1h · closes daily bars","tech":"Python 3.12","kind":"service"},
    {"id":"watchdog","label":"bin/run_watchdog.py","sub":"freshness of 85 collections","tech":"Python 3.12","kind":"service"},
    {"id":"pipeline","label":"pipeline.py","sub":"orchestration · per-token isolation","tech":"pandas","kind":"module"},
    {"id":"extract","label":"extract.py","sub":"spot candles · 429 backoff","tech":"ccxt 4.5.40","kind":"module"},
    {"id":"perp","label":"extract_perp.py","sub":"perp candles + funding","tech":"ccxt.kucoinfutures","kind":"module"},
    {"id":"sentiment","label":"sentiment.py","sub":"Fear & Greed","tech":"requests","kind":"module"},
    {"id":"indicators","label":"indicators.py","sub":"~85 indicators · single source","tech":"pandas-ta-classic","kind":"module"},
    {"id":"db","label":"db.py","sub":"bulk upsert · unique on timestamp","tech":"pymongo","kind":"module"},
    {"id":"spot_api","label":"KuCoin spot","sub":"public endpoints, no key","tech":"REST","kind":"external"},
    {"id":"perp_api","label":"KuCoin Futures","sub":"~2-day funding dead zone","tech":"REST","kind":"external"},
    {"id":"fng","label":"alternative.me","sub":"Fear & Greed Index","tech":"REST","kind":"external"},
    {"id":"mongo","label":"MongoDB","sub":"~110 collections · btc_data","tech":"MongoDB 7 · Docker","kind":"store"},
    {"id":"cra","label":"Crypto_Research_Assistant","sub":"reads, never writes","tech":"Python 3.12","kind":"external"}
  ],
  "edges": [
    {"from":"launchd","to":"daily","style":"static"},
    {"from":"launchd","to":"hourly","style":"static"},
    {"from":"launchd","to":"watchdog","style":"static"},
    {"from":"daily","to":"pipeline"},
    {"from":"hourly","to":"pipeline"},
    {"from":"pipeline","to":"extract"},
    {"from":"pipeline","to":"perp"},
    {"from":"pipeline","to":"sentiment"},
    {"from":"pipeline","to":"indicators","label":"compute_all()"},
    {"from":"extract","to":"spot_api","label":"OHLCV"},
    {"from":"perp","to":"perp_api","label":"OHLCV + funding"},
    {"from":"sentiment","to":"fng"},
    {"from":"indicators","to":"db"},
    {"from":"db","to":"mongo","label":"upsert closed bars only"},
    {"from":"watchdog","to":"mongo","label":"freshness check"},
    {"from":"mongo","to":"cra","label":"the column contract"}
  ]
}
```

**Only closed candles are written.** `run_update` bounds its window by
`_last_closed_period()`; before 2026-07-19 it stored the forming candle and the
gap check then skipped it forever. Indicator column names are a public API —
renaming one is a cross-repo change ([ADR-001](../../docs/decisions/001-indicator-columns-as-public-api.md)).

## Data Pipeline

Every token and timeframe runs the same seven steps, orchestrated by
`pipeline.py`. Pick a flow to walk it.

```archview
{
  "id": "pipeline",
  "caption": "One incremental run, for one token and one timeframe.",
  "nodes": [
    {"id": "load", "label": "Load window", "sub": "last 200 rows", "kind": "store"},
    {"id": "gaps", "label": "Detect gaps", "sub": "newest stored vs now", "kind": "module"},
    {"id": "fetch", "label": "Fetch candles", "sub": "KuCoin via CCXT", "kind": "external"},
    {"id": "append", "label": "Append", "sub": "onto the window", "kind": "module"},
    {"id": "indicators", "label": "Recompute indicators", "sub": "compute_all", "kind": "module"},
    {"id": "fng", "label": "Fear and Greed", "sub": "alternative.me", "kind": "external"},
    {"id": "upsert", "label": "Bulk upsert", "sub": "new rows only", "kind": "store"}
  ],
  "edges": [
    {"from": "load", "to": "gaps"},
    {"from": "gaps", "to": "fetch"},
    {"from": "fetch", "to": "append"},
    {"from": "append", "to": "indicators"},
    {"from": "indicators", "to": "fng"},
    {"from": "fng", "to": "upsert"}
  ]
}
```

```archflow
{
  "view": "pipeline",
  "flows": [
    {
      "id": "incremental",
      "label": "An incremental run",
      "steps": [
        {"node": "load", "note": "The last 200 rows come back as a sliding window — enough for every indicator's warmup without loading the whole collection."},
        {"node": "gaps", "note": "The newest stored timestamp is compared against now. Only the difference has to be fetched; everything else is already correct."},
        {"node": "fetch", "note": "Missing candles are pulled from KuCoin via CCXT (extract.py), bounded by _last_closed_period() so a forming candle is never stored."},
        {"node": "append", "note": "New candles join the window DataFrame. Nothing is written yet."},
        {"node": "indicators", "note": "indicators.compute_all() recomputes every column over the window. It is the single source of truth — no other code may produce an indicator."},
        {"node": "fng", "note": "The Fear & Greed Index is fetched separately from alternative.me (sentiment.py), so a failure here does not cost you the candles."},
        {"node": "upsert", "note": "Only the newly fetched rows are upserted, and any row still holding a NaN indicator is skipped rather than stored incomplete."}
      ]
    }
  ]
}
```

## Deep Historical Backfill (`backfill.py`)

A one-time operation to pull the maximum history KuCoin will give. Safe to
re-run — upsert semantics, per-token error isolation, resumable.

```archview
{
  "id": "backfill",
  "caption": "The one-time deep fetch. Existing rows win every collision.",
  "nodes": [
    {"id": "since", "label": "Determine start", "sub": "Oct 2017 daily, Jan 2020 intraday", "kind": "module"},
    {"id": "pull", "label": "Fetch all candles", "sub": "paginated batches", "kind": "external"},
    {"id": "existing", "label": "Load existing", "sub": "OHLCV only", "kind": "store"},
    {"id": "merge", "label": "Merge", "sub": "existing wins on conflict", "kind": "module"},
    {"id": "recompute", "label": "Recompute indicators", "sub": "over the full set", "kind": "module"},
    {"id": "warmup", "label": "Drop warmup rows", "sub": "NaN out, FnG null", "kind": "module"},
    {"id": "chunk", "label": "Chunked upsert", "sub": "5K-doc batches", "kind": "store"}
  ],
  "edges": [
    {"from": "since", "to": "pull"},
    {"from": "pull", "to": "existing"},
    {"from": "existing", "to": "merge"},
    {"from": "merge", "to": "recompute"},
    {"from": "recompute", "to": "warmup"},
    {"from": "warmup", "to": "chunk"}
  ]
}
```

```archflow
{
  "view": "backfill",
  "flows": [
    {
      "id": "deep",
      "label": "A deep backfill",
      "steps": [
        {"node": "since", "note": "Oct 2017 for daily, Jan 2020 for 4h/1h, or whatever --since says."},
        {"node": "pull", "note": "Everything from that date is fetched in paginated batches."},
        {"node": "existing", "note": "What is already stored is loaded — OHLCV only, via load_all()."},
        {"node": "merge", "note": "Deduplicated on timestamp, and existing OHLCV wins every conflict. This is why backfill CANNOT repair the pre-2026-07-19 truncated closes — it keeps the wrong row."},
        {"node": "recompute", "note": "Indicators are recomputed across the whole merged dataset, not just the new part."},
        {"node": "warmup", "note": "Rows whose indicators never warmed up are dropped, and Fear & Greed is set to None for history it does not cover."},
        {"node": "chunk", "note": "Written in 5K-document batches via bulk_upsert_chunked() so a large token cannot blow up the write."}
      ]
    }
  ]
}
```

## MongoDB Schema

- Database: `btc_data` (production), `btc_data_test` (testing)
- **Spot:** `{token}_daily_price_data`, `{token}_weekly_price_data`, `{token}_1h_price_data` — 17 each. Newer tokens (SUI/WIF) have partial indicators (SMA_200/EMA_200 null until ~200 weeks history).
- **Perp:** `{token}_perp_daily_price_data`, `{token}_perp_1h_price_data` — 17 each. No weekly (KuCoin Futures limitation). Perp 1h limited to ~15 months by exchange.
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
| `config.py` | TOKENS (17), TIMEFRAMES, MARKET_TYPES, PERP_SYMBOL_MAP, DB names, collection name mapping |
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
