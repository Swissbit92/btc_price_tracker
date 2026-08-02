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

```archstat
[
  {
    "label": "Tokens",
    "value": "17",
    "note": "spot + perp"
  },
  {
    "label": "Indicators",
    "value": "85",
    "note": "public API",
    "state": "warn"
  },
  {
    "label": "Writes",
    "value": "Owner",
    "note": "price collections",
    "state": "bad"
  },
  {
    "label": "Closed bars",
    "value": "Only",
    "note": "since 2026-07-19",
    "state": "ok"
  },
  {
    "label": "Cadence",
    "value": "03:10",
    "note": "+ hourly :05"
  }
]
```

## Topology

```archview
{
  "caption": "Three launchd jobs, one shared pipeline, and the collections every downstream repo reads.",
  "nodes": [
    {
      "id": "launchd",
      "label": "launchd",
      "sub": "daily 03:10 \u00b7 hourly :05 \u00b7 watchdog 07:00",
      "tech": "plist \u00b7 local time",
      "kind": "external",
      "note": "Fires all three jobs in machine local time. The daily moved to 03:10 because 01:10 sat on the wrong side of the UTC day boundary under CEST."
    },
    {
      "id": "daily",
      "label": "bin/run_daily.py",
      "sub": "spot + perp + weekly + CSV",
      "tech": "Python 3.12",
      "kind": "service",
      "note": "Spot, perp, weekly and the CSV export, once a day."
    },
    {
      "id": "hourly",
      "label": "bin/run_hourly.py",
      "sub": "17 tokens 1h \u00b7 closes daily bars",
      "tech": "Python 3.12",
      "kind": "service",
      "note": "The 1h bars \u2014 and it also closes the daily and weekly ones, so correctness no longer depends on the daily job firing."
    },
    {
      "id": "watchdog",
      "label": "bin/run_watchdog.py",
      "sub": "freshness of 85 collections",
      "tech": "Python 3.12",
      "kind": "service",
      "note": "Independent freshness check across 85 collections. It exists because a pipeline that stops silently looks exactly like one with nothing to do."
    },
    {
      "id": "pipeline",
      "label": "pipeline.py",
      "sub": "orchestration \u00b7 per-token isolation",
      "tech": "pandas",
      "kind": "module",
      "note": "Orchestrates one token at a time, isolated, so one bad symbol cannot take the run down."
    },
    {
      "id": "extract",
      "label": "extract.py",
      "sub": "spot candles \u00b7 429 backoff",
      "tech": "ccxt 4.5.40",
      "kind": "module",
      "note": "Spot candles via CCXT, retrying 429s \u2014 which KuCoin misreports as a generic exchange error."
    },
    {
      "id": "perp",
      "label": "extract_perp.py",
      "sub": "perp candles + funding",
      "tech": "ccxt.kucoinfutures",
      "kind": "module",
      "note": "Perp candles and funding. Funding has a roughly two-day dead zone at the recent end."
    },
    {
      "id": "sentiment",
      "label": "sentiment.py",
      "sub": "Fear & Greed",
      "tech": "requests",
      "kind": "module",
      "note": "Fetches the Fear and Greed index, separately, so its outage costs no candles."
    },
    {
      "id": "indicators",
      "label": "indicators.py",
      "sub": "~85 indicators \u00b7 single source",
      "tech": "pandas-ta-classic",
      "kind": "module",
      "note": "compute_all() is the single source of truth for every column. No other code may produce an indicator."
    },
    {
      "id": "db",
      "label": "db.py",
      "sub": "bulk upsert \u00b7 unique on timestamp",
      "tech": "pymongo",
      "kind": "module",
      "note": "Bulk upsert with a unique index on timestamp, which is what makes a re-run harmless."
    },
    {
      "id": "spot_api",
      "label": "KuCoin spot",
      "sub": "public endpoints, no key",
      "tech": "REST",
      "kind": "external",
      "note": "Public endpoints only \u2014 no key, no signing."
    },
    {
      "id": "perp_api",
      "label": "KuCoin Futures",
      "sub": "~2-day funding dead zone",
      "tech": "REST",
      "kind": "external",
      "note": "The futures venue, same story plus funding."
    },
    {
      "id": "fng",
      "label": "alternative.me",
      "sub": "Fear & Greed Index",
      "tech": "REST",
      "kind": "external",
      "note": "Fear and Greed comes from a separate API, so an outage there does not cost you the candles."
    },
    {
      "id": "mongo",
      "label": "MongoDB",
      "sub": "~110 collections \u00b7 btc_data",
      "tech": "MongoDB 7 \u00b7 Docker",
      "kind": "store",
      "note": "Around 110 collections. This repo is the only writer to the price ones."
    },
    {
      "id": "cra",
      "label": "Crypto_Research_Assistant",
      "sub": "reads, never writes",
      "tech": "Python 3.12",
      "kind": "external",
      "note": "Reads the columns this repo writes. That column list is the contract between them."
    }
  ],
  "edges": [
    {
      "from": "launchd",
      "to": "daily",
      "style": "static"
    },
    {
      "from": "launchd",
      "to": "hourly",
      "style": "static"
    },
    {
      "from": "launchd",
      "to": "watchdog",
      "style": "static"
    },
    {
      "from": "daily",
      "to": "pipeline"
    },
    {
      "from": "hourly",
      "to": "pipeline"
    },
    {
      "from": "pipeline",
      "to": "extract"
    },
    {
      "from": "pipeline",
      "to": "perp"
    },
    {
      "from": "pipeline",
      "to": "sentiment"
    },
    {
      "from": "pipeline",
      "to": "indicators",
      "label": "compute_all()"
    },
    {
      "from": "extract",
      "to": "spot_api",
      "label": "OHLCV"
    },
    {
      "from": "perp",
      "to": "perp_api",
      "label": "OHLCV + funding"
    },
    {
      "from": "sentiment",
      "to": "fng"
    },
    {
      "from": "indicators",
      "to": "db"
    },
    {
      "from": "db",
      "to": "mongo",
      "label": "upsert closed bars only"
    },
    {
      "from": "watchdog",
      "to": "mongo",
      "label": "freshness check"
    },
    {
      "from": "mongo",
      "to": "cra",
      "label": "the column contract"
    }
  ]
}
```

**Only closed candles are written.** `run_update` bounds its window by
`_last_closed_period()`; before 2026-07-19 it stored the forming candle and the
gap check then skipped it forever.

```archplot
{
  "id": "truncated",
  "schematic": true,
  "height": 250,
  "xlabel": "one daily period →",
  "alt": "An intraday price, the moment the row was written, and the gap between the close it recorded and the real one",
  "caption": "The row was written before the period ended, so the Close it stored was a mid-bar price — everything after the red line was thrown away. The gap check then saw a row already present and never came back, which is why the error was silent, and why `backfill.py` cannot repair it: existing rows win every collision.",
  "series": [
    {
      "label": "price",
      "tone": "ink",
      "points": [
        100.02,
        100.3,
        100.09,
        100.31,
        100.25,
        100.19,
        100.61,
        100.65,
        100.64,
        100.8,
        101.05,
        101.04,
        101.17,
        100.95,
        100.87,
        100.78,
        100.48,
        100.15,
        99.79,
        99.74,
        99.7,
        99.63,
        99.65,
        99.36,
        99.34,
        99.39,
        99.56,
        99.37,
        99.28,
        98.84,
        98.73,
        98.24,
        97.93,
        98.17,
        97.69,
        97.87,
        97.94,
        97.87,
        97.97,
        98.09,
        98.32,
        98.26,
        98.13,
        98.0,
        97.78,
        97.77,
        97.6,
        97.84,
        97.43,
        97.19,
        96.98,
        96.51,
        96.93,
        96.4,
        96.34,
        96.23,
        96.59,
        96.15,
        96.39,
        96.23,
        96.19,
        96.05,
        96.19,
        95.94,
        95.92,
        96.0,
        96.4,
        95.87,
        96.21,
        96.42,
        96.31,
        96.38,
        96.28,
        96.64,
        96.68,
        96.64,
        96.59,
        96.54,
        96.5,
        95.89,
        95.92,
        95.08,
        93.87,
        93.42,
        92.97,
        92.63,
        92.17,
        91.71,
        91.37,
        91.16,
        90.64,
        90.14,
        90.15,
        89.84,
        89.21,
        89.3
      ]
    }
  ],
  "thresholds": [
    {
      "value": 96.5,
      "label": "Close, recorded",
      "tone": "bad"
    },
    {
      "value": 89.3,
      "label": "Close, actual",
      "tone": "good"
    }
  ],
  "marks": [
    {
      "at": 78,
      "label": "row written",
      "tone": "bad"
    },
    {
      "at": 95,
      "label": "period closes",
      "tone": "good"
    }
  ]
}
```
 Indicator column names are a public API —
renaming one is a cross-repo change ([ADR-001](../../docs/decisions/001-indicator-columns-as-public-api.md)).

## Data Pipeline

Every token and timeframe runs the same seven steps, orchestrated by
`pipeline.py`. Pick a flow to walk it.

```archview
{
  "id": "pipeline",
  "caption": "One incremental run, for one token and one timeframe.",
  "nodes": [
    {
      "id": "load",
      "label": "Load window",
      "sub": "last 200 rows",
      "kind": "store",
      "note": "Pulls the last 200 rows as a sliding window \u2014 enough for every indicator's warmup without reading the whole collection."
    },
    {
      "id": "gaps",
      "label": "Detect gaps",
      "sub": "newest stored vs now",
      "kind": "module",
      "note": "Compares the newest stored timestamp against now. Only the difference has to be fetched."
    },
    {
      "id": "fetch",
      "label": "Fetch candles",
      "sub": "KuCoin via CCXT",
      "kind": "external",
      "note": "Pulls the missing candles, bounded by the last closed period so a forming candle is never stored."
    },
    {
      "id": "append",
      "label": "Append",
      "sub": "onto the window",
      "kind": "module",
      "note": "New candles join the window in memory. Nothing is written yet."
    },
    {
      "id": "indicators",
      "label": "Recompute indicators",
      "sub": "compute_all",
      "kind": "module",
      "note": "compute_all() is the single source of truth for every column. No other code may produce an indicator."
    },
    {
      "id": "fng",
      "label": "Fear and Greed",
      "sub": "alternative.me",
      "kind": "external",
      "note": "Fear and Greed comes from a separate API, so an outage there does not cost you the candles."
    },
    {
      "id": "upsert",
      "label": "Bulk upsert",
      "sub": "new rows only",
      "kind": "store",
      "note": "Writes only the new rows, and skips any still carrying a NaN rather than storing it incomplete."
    }
  ],
  "edges": [
    {
      "from": "load",
      "to": "gaps"
    },
    {
      "from": "gaps",
      "to": "fetch"
    },
    {
      "from": "fetch",
      "to": "append"
    },
    {
      "from": "append",
      "to": "indicators"
    },
    {
      "from": "indicators",
      "to": "fng"
    },
    {
      "from": "fng",
      "to": "upsert"
    }
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
    {
      "id": "since",
      "label": "Determine start",
      "sub": "Oct 2017 daily, Jan 2020 intraday",
      "kind": "module",
      "note": "Oct 2017 for daily, Jan 2020 for intraday, or whatever --since says."
    },
    {
      "id": "pull",
      "label": "Fetch all candles",
      "sub": "paginated batches",
      "kind": "external",
      "note": "Everything from that date, in paginated batches."
    },
    {
      "id": "existing",
      "label": "Load existing",
      "sub": "OHLCV only",
      "kind": "store",
      "note": "Loads what is already stored \u2014 OHLCV only."
    },
    {
      "id": "merge",
      "label": "Merge",
      "sub": "existing wins on conflict",
      "kind": "module",
      "note": "Existing rows win every collision. This is exactly why backfill cannot repair the pre-2026-07-19 truncated closes."
    },
    {
      "id": "recompute",
      "label": "Recompute indicators",
      "sub": "over the full set",
      "kind": "module",
      "note": "Indicators are recomputed across the whole merged set, not just the new part."
    },
    {
      "id": "warmup",
      "label": "Drop warmup rows",
      "sub": "NaN out, FnG null",
      "kind": "module",
      "note": "Rows whose indicators never warmed up are dropped rather than stored half-formed."
    },
    {
      "id": "chunk",
      "label": "Chunked upsert",
      "sub": "5K-doc batches",
      "kind": "store",
      "note": "5K-document batches, so a large token cannot blow up the write."
    }
  ],
  "edges": [
    {
      "from": "since",
      "to": "pull"
    },
    {
      "from": "pull",
      "to": "existing"
    },
    {
      "from": "existing",
      "to": "merge"
    },
    {
      "from": "merge",
      "to": "recompute"
    },
    {
      "from": "recompute",
      "to": "warmup"
    },
    {
      "from": "warmup",
      "to": "chunk"
    }
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

## Glossary

The indicator names are a public API, so the vocabulary below is load-bearing —
a reader who guesses at these will guess wrong about the contract.

| Term | What it means here |
|---|---|
| **OHLCV** | Open, high, low, close, volume — one candle |
| **Closed vs forming candle** | A closed candle covers a finished period. A forming one is still moving, and storing it was the bug that made 76% of daily closes wrong before 2026-07-19 |
| **Sliding window** | The last 200 rows, loaded per run. Enough for the longest indicator warmup without reading the whole collection |
| **Warmup** | The leading rows where a long-period indicator has no value yet. Dropped rather than stored as null |
| **Perp** | Perpetual futures — no expiry, and the funding rate is what keeps it near spot |
| **Funding rate** | The periodic payment between longs and shorts on a perp. Positive means longs pay |
| **Backfill** | The one-time deep history fetch. Its merge keeps existing rows, so it cannot repair bad ones |
| **Upsert** | Insert-or-update keyed on timestamp, which is what makes a re-run harmless |
| **FnG** | The Fear and Greed index, fetched separately from price |
| **Lean XS universe** | ~283 extra tokens ingested with prices and funding but no indicators, for cross-sectional research only. Deliberately outside `config.TOKENS` |
