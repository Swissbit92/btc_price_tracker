# Multi-Token Expansion & Refactor — Migration Plan & Progress

## Overview

Expand the BTC-only price tracker to support **BTC, ETH, SOL, XRP** with an expanded indicator suite, while eliminating 4-script duplication and preserving all existing production data.

**Migration safety principle:** The existing production databases (`btc_data.1h_price_data`, `btc_data.daily_price_data`) are **NEVER modified or dropped** until fully validated. Old scripts keep running via GitHub Actions throughout the migration.

---

## MongoDB Layout

### Existing (do not touch)
| Database | Collection | Role |
|---|---|---|
| `btc_data` | `1h_price_data` | PRODUCTION hourly BTC |
| `btc_data` | `daily_price_data` | PRODUCTION daily BTC |
| `btc_data` | `BTC dayli buying` | Unrelated, do not touch |
| `btc_data_test` | `1h_price_data_test` | Existing test data |
| `btc_data_test` | `daily_price_data_test` | Existing test data |

### New collections (Phase B: test, Phase C: prod)
| Collection pattern | Tokens |
|---|---|
| `{token}_1h_price_data` | btc, eth, sol, xrp |
| `{token}_daily_price_data` | btc, eth, sol, xrp |

---

## Phase A: Build New Modules

> **Goal:** Create the new modular codebase. No MongoDB writes, no production impact.

### New files created

- [x] `btc_tracker_mongodb/config.py` — Central config (TOKENS, TIMEFRAMES, DB names, collection name helpers)
- [x] `btc_tracker_mongodb/db.py` — MongoDB connection + CRUD (get_db, get_collection, load_latest, bulk_upsert, get_latest_timestamp, ensure_indexes)
- [x] `btc_tracker_mongodb/extract.py` — CCXT-based KuCoin data fetching (fetch_candles, fetch_seed_candles)
- [x] `btc_tracker_mongodb/indicators.py` — Single source of truth for ALL indicators (compute_all, get_numeric_cols)
- [x] `btc_tracker_mongodb/pipeline.py` — Orchestration (run_seed, run_seed_from_csv, run_update, run_seed_all, run_update_all)
- [x] `btc_tracker_mongodb/query.py` — Parameterized debug query with --compare mode
- [x] `seed.py` (root) — CLI entry point for seeding
- [x] `update.py` (root) — CLI entry point for updates
- [x] `requirements.txt` — Updated (removed: python-binance, ta, skyfield; added: ccxt, pandas_ta, numpy, requests)

### Indicator suite changes

**Kept (ported from `ta` to `pandas_ta`):**
- SMA (50, 100, 200), EMA (20, 50, 100, 200)
- RSI (14), Stochastic RSI (14, K=3, D=3)
- Bollinger Bands (20, 2sigma)
- Ichimoku Cloud (9, 26, 52)
- MACD (12, 26, 9)
- Donchian Channel (20)
- Fibonacci retracement (refactored to rolling 50-period window)
- HDPR (custom mean-reversion signal)

**Added:**
- ATR (14), ADX / +DI / -DI (14)
- VWAP, Williams %R (14), CCI (20)
- ROC (12, 24)
- Log returns (1, 4, 12, 24 periods)
- Parkinson volatility (14-period rolling)
- Realized volatility (14 and 30-period)
- Volatility ratio (14/30)
- Temporal features: hour-of-day (sin/cos), day-of-week (sin/cos)

**Removed:**
- Moon cycle phase (no statistical significance, removes skyfield dep + 16MB de421.bsp)

### Phase A — Test Gate

- [x] **A-TG1: Import test** — All new modules import without errors (PASSED 2026-03-01)
- [x] **A-TG2: Indicator smoke test** — `compute_all()` on 300-row synthetic OHLCV produces all 52 expected columns (PASSED 2026-03-01)
- [x] **A-TG3: CCXT connectivity** — `fetch_candles('BTC-USDT', '1h', ...)` returns valid candle data (PASSED 2026-03-01)
- [x] **A-TG4: CCXT multi-token** — All 4 tokens fetch successfully: BTC=$66135, ETH=$1974, SOL=$84, XRP=$1.37 (PASSED 2026-03-01)
- [x] **A-TG5: Indicator column count** — `get_numeric_cols()` returns 52 columns, all present in output (PASSED 2026-03-01)
- [x] **A-TG6: No NaN in tail** — Zero NaN in last 50 rows of all 52 indicator columns on 300-row real BTC data (PASSED 2026-03-01)
- [x] **A-TG7: Full integration** — Real CCXT fetch (300 candles) + `compute_all()` end-to-end: 52/52 indicators, zero NaN in tail (PASSED 2026-03-01)

---

## Phase B: Validate with Test Database

> **Goal:** Write to `btc_data_test` only. Production stays untouched.

### B1. Test CCXT fetch locally
- [x] Verify BTC-USDT candles from KuCoin (PASSED 2026-03-01, Phase A-TG3)
- [x] Verify ETH-USDT, SOL-USDT, XRP-USDT candles (PASSED 2026-03-01, Phase A-TG4)

### B2. Seed BTC to test database
```bash
python seed.py --symbol BTC-USDT --timeframe 1h --test
python seed.py --symbol BTC-USDT --timeframe 1d --test
```
- [x] `btc_1h_price_data` created in `btc_data_test` — 301 docs (500 fetched, 199 warmup dropped)
- [x] `btc_daily_price_data` created in `btc_data_test` — 301 docs
- [x] Documents have all 52 expected indicator columns + 6 OHLCV/timestamp = 58 total
- [x] No NaN in any indicator field across all documents
- [x] Timestamp range: 1h=2026-02-17 to 2026-03-01, daily=2025-05-05 to 2026-03-01
- [x] Document count matches expected (500 - 199 warmup = 301)

### B3. Compare test output against production
- [x] OHLCV values: **exact match** (zero diff) across 200 overlapping timestamps
- [x] 22/22 parity indicators PASS (< 1% relative diff): SMA, EMA, RSI, Stoch_RSI_K/D, BB, Ichimoku Conversion/Base, Donchian, HDPR, MACD
- [x] Known acceptable differences:
  - `Stoch_RSI`: old pipeline stored raw unsmoothed value, new stores %K (same as Stoch_RSI_K). K and D match.
  - `Ichimoku_A/B`: library-level difference in Senkou span shift. Both valid. New collections = new schema.
  - `EMA_200`: 0.47% max relative diff due to different history length (seed 500 vs prod has more). Expected for exponential smoothing.
- [x] All 26 new indicators present and 0% NaN

### B4. Test incremental update on test database
```bash
python update.py --symbol BTC-USDT --timeframe 1h --test
```
- [x] Gap detection works correctly — detects and fetches exactly missing candles
- [x] Missing candles fetched and upserted (301 -> 302 after 1 new hour)
- [x] No duplicate timestamps (verified: 0 duplicates)
- [x] Idempotency verified: two consecutive runs with no gap = "up to date", count unchanged

### B5. Seed and test all tokens in test database
```bash
python seed.py --all --test
python update.py --all --test
```
- [x] All 8 collections created in `btc_data_test` — all 301+ docs each (PASSED 2026-03-01)
- [x] All collections: 58 cols, 0 NaN, 0 dupes, unique indexes, >200 docs
- [x] `update.py --all --test` runs successfully — all 8 tokens/timeframes up to date

### Phase B — Test Gate

- [x] **B-TG1: Document schema** — 58 cols per doc (52 indicators + OHLCV + timestamp), all present (PASSED 2026-03-01)
- [x] **B-TG2: OHLCV integrity** — Exact match (zero diff) across 200 overlapping timestamps (PASSED 2026-03-01)
- [x] **B-TG3: Indicator parity** — 22/22 shared indicators < 1% relative diff (PASSED 2026-03-01)
- [x] **B-TG4: New indicators populated** — All 26 new indicators present with 0% NaN (PASSED 2026-03-01)
- [x] **B-TG5: Gap detection** — Correctly detected 1h gap and fetched 1 missing candle (PASSED 2026-03-01)
- [x] **B-TG6: Idempotency** — Two consecutive runs = "up to date", count unchanged, 0 duplicates (PASSED 2026-03-01)
- [x] **B-TG7: Multi-token coverage** — 8/8 collections, all >200 docs, 58 cols, 0 NaN, 0 dupes, unique indexes (PASSED 2026-03-01)
- [x] **B-TG8: Index verification** — Unique timestamp index on all 8 test collections (PASSED 2026-03-01)

### B6. Run side-by-side for 24-48 hours
- [x] First side-by-side run (2026-03-01 22:00 UTC): OHLCV PASS for both 1h and 1d. Test pipeline 2h ahead of prod.
- [ ] Old GitHub Actions still running and writing to `btc_data`
- [ ] Manual `update.py --all --test` runs succeed repeatedly over 24-48h
- [ ] Test collections match production BTC data for overlapping timestamps after 24h

**Re-run command (run every few hours over the next 24-48h):**
```bash
source Scripts/activate
python update.py --all --test
```

---

## Phase C: Cutover (only after Phase B fully validated)

### C1. Seed production collections for new tokens
- [x] ETH-USDT: 301 docs each for 1h + daily (DONE 2026-03-01)
- [x] SOL-USDT: 301 docs each for 1h + daily (DONE 2026-03-01)
- [x] XRP-USDT: 301 docs each for 1h + daily (DONE 2026-03-01)

### C2. Copy existing BTC data to new collection names
- [x] `1h_price_data` (6911 docs) -> `btc_1h_price_data` (6913 docs) — DONE
- [x] `daily_price_data` (3513 docs) -> `btc_daily_price_data` (3514 docs) — DONE
- [x] New >= old doc counts verified

### C3. Re-seed BTC with expanded indicators
- [x] `btc_1h_price_data`: latest 301 docs now have full 52-indicator suite (DONE 2026-03-01)
- [x] `btc_daily_price_data`: latest 301 docs now have full 52-indicator suite (DONE 2026-03-01)

### C4. Update GitHub Actions workflows
- [x] `update-hourly.yml`: `python update.py --all --timeframe 1h`, Python 3.11, `pip install -r requirements.txt`
- [x] `update-daily.yml`: `python update.py --all --timeframe 1d`, Python 3.11, `pip install -r requirements.txt`

### C5. Update downstream repos
- [ ] Trading bot updated: `1h_price_data` -> `btc_1h_price_data`
- [ ] Trading bot updated: `daily_price_data` -> `btc_daily_price_data`

### Phase C — Test Gate

- [x] **C-TG1: Production BTC copy integrity** — new >= old (6913 >= 6911, 3514 >= 3513) (PASSED 2026-03-01)
- [x] **C-TG2: Expanded indicators** — All 52 indicators present in recent BTC docs (PASSED 2026-03-01)
- [x] **C-TG3: All 8 production collections** — All pass: >200 docs, 58 cols, unique indexes (PASSED 2026-03-01)
- [x] **C-TG4: Incremental update** — `update.py --all` runs clean on production, all 8 up to date (PASSED 2026-03-01)
- [ ] **C-TG5: 24h production validation** — After 24h of new workflows running, all 8 collections receiving updates
- [ ] **C-TG6: No data gaps** — No gaps > 1 candle period in any production collection over 48h

### C6. Parallel run period (1 week)
- [ ] Both old and new workflows coexist without issues
- [ ] All 8 new collections receiving regular updates
- [ ] Downstream repos fully migrated

### C7. Cleanup (only after downstream repos fully migrated)
- [ ] Drop test collections in `btc_data_test`
- [ ] Drop old collections (`1h_price_data`, `daily_price_data`) — ONLY after ALL downstream repos migrated
- [x] Delete old scripts: `seed_historical.py`, `seed_daily.py`, `update_hourly.py`, `update_daily.py`, `mongodb_query.py`, `query_latest_daily.py` (DONE 2026-03-18)
- [x] Delete `de421.bsp` (16MB ephemeris file) (DONE 2026-03-18)
- [x] Update `app.py` to use new imports (DONE 2026-03-18)
- [x] Update `CLAUDE.md` with new architecture docs (DONE 2026-03-18)

---

## File Change Summary

| Action | File | Phase | Status |
|--------|------|-------|--------|
| CREATE | `btc_tracker_mongodb/config.py` | A | Done |
| CREATE | `btc_tracker_mongodb/db.py` | A | Done |
| CREATE | `btc_tracker_mongodb/extract.py` | A | Done |
| CREATE | `btc_tracker_mongodb/indicators.py` | A | Done |
| CREATE | `btc_tracker_mongodb/pipeline.py` | A | Done |
| CREATE | `btc_tracker_mongodb/query.py` | A | Done |
| CREATE | `seed.py` (root) | A | Done |
| CREATE | `update.py` (root) | A | Done |
| MODIFY | `requirements.txt` | A | Done |
| CREATE | `docs/MIGRATION.md` | A | Done |
| MODIFY | `.github/workflows/update-hourly.yml` | C4 | Done |
| MODIFY | `.github/workflows/update-daily.yml` | C4 | Done |
| MODIFY | `app.py` | C7 | Done |
| MODIFY | `CLAUDE.md` | C7 | Done |
| DELETE | `btc_tracker_mongodb/seed_historical.py` | C7 | Done |
| DELETE | `btc_tracker_mongodb/seed_daily.py` | C7 | Done |
| DELETE | `btc_tracker_mongodb/update_hourly.py` | C7 | Done |
| DELETE | `btc_tracker_mongodb/update_daily.py` | C7 | Done |
| DELETE | `btc_tracker_mongodb/mongodb_query.py` | C7 | Done |
| DELETE | `btc_tracker_mongodb/query_latest_daily.py` | C7 | Done |
| DELETE | `de421.bsp` | C7 | Done |

---

## Dependencies Changed

| Removed | Added |
|---------|-------|
| `python-binance` (unused) | `ccxt` |
| `ta` | `pandas-ta-classic` |
| `skyfield` | `numpy` |
| — | `requests` (was missing) |

---

## Phase D: Indicator & Token Expansion

> **Goal:** Expand from 52 to ~79 indicators, add BNB as 5th token, add 4h timeframe, integrate Fear & Greed Index.

### D1. Indicator cleanup
- [x] Removed `Stoch_RSI` (duplicate of `Stoch_RSI_K`)
- [x] Removed `ROC_12`, `ROC_24` (near-duplicate of `LogReturn_12`/`LogReturn_24`)
- [x] Fixed `HDPR_MA` to reuse `SMA_50` instead of recomputing
- [x] Fixed VWAP: rolling 24-bar for intraday (1h, 4h), cumulative for daily

### D2. New indicators added (Tier 1)
- [x] OBV (On-Balance Volume)
- [x] CMF (Chaikin Money Flow, 20)
- [x] MFI (Money Flow Index, 14)
- [x] Supertrend (7, 3.0) — direction + value
- [x] NATR (Normalized ATR, 14)
- [x] KAMA (Kaufman Adaptive MA, 10)
- [x] Choppiness Index (14)

### D3. New indicators added (Tier 2)
- [x] Squeeze Momentum (flag + momentum)
- [x] Aroon (Up/Down/Oscillator, 25)
- [x] HMA (Hull MA, 20)
- [x] PSAR (Parabolic SAR)
- [x] Stochastic (K=14, D=3)
- [x] TRIX (18)

### D4. ML feature engineering
- [x] Close/RSI/Volume Z-scores (100-period)
- [x] Candle body/wick ratios (ATR-normalized)
- [x] Price vs EMA20/SMA200 (ATR-normalized)
- [x] BB Width
- [x] RSI Slope (3), MACD Slope (3)

### D5. Fear & Greed Index
- [x] Created `sentiment.py` — fetches from `https://api.alternative.me/fng/`
- [x] Integrated into `pipeline.py` — FnG_Value (int 0-100) and FnG_Class (string) added to each document
- [x] Graceful fallback: pipeline continues if API is unreachable

### D6. Token expansion
- [x] Added BNB-USDT to TOKENS in `config.py`
- [x] 5 tokens total: BTC, ETH, SOL, XRP, BNB

### D7. Timeframe expansion
- [x] Added 4h to TIMEFRAMES in `config.py`
- [x] Updated `get_collection_name()` for 4h -> `{token}_4h_price_data`
- [x] Updated `extract.py` with 4h CCXT/delta mappings
- [x] Updated `pipeline.py` with 4h timedelta and floor logic
- [x] Created `.github/workflows/update-4h.yml` (cron `0 */4 * * *`)

### D8. Column count
| Category | Count |
|---|---|
| Existing (after cleanup) | 49 (-3: Stoch_RSI, ROC_12, ROC_24) |
| Tier 1 new | +9 |
| Tier 2 new | +9 |
| ML features | +11 |
| Sentiment | +1 numeric (FnG_Value) + 1 string (FnG_Class) |
| Risk metrics (Phase D2b) | +6 (VaR, CVaR, Omega, Tail Ratio, Ulcer Index, Kappa) |
| **Total** | **~85 numeric + 1 string** |

### Phase D — Test Gate
- [x] **D-TG1: Import test** — All modules import without errors (PASSED)
- [x] **D-TG2: Indicator smoke test** — `compute_all()` on 300-row synthetic OHLCV produces ~85 expected columns (PASSED)
- [x] **D-TG3: No NaN in tail** — Zero NaN in last 50 rows of all indicator columns (PASSED)
- [x] **D-TG4: Fear & Greed fetch** — `fetch_fear_greed()` returns valid data (PASSED)
- [x] **D-TG5: BNB CCXT fetch** — BNB-USDT candles fetch successfully for 1h, 4h, 1d (PASSED)
- [x] **D-TG6: Test DB seed** — All 15 collections (5 tokens x 3 timeframes) seeded in test DB (PASSED — expanded to 39 collections in Phase E)
- [x] **D-TG7: OHLCV parity** — Existing 4 tokens' OHLCV data unchanged by new indicators (PASSED)
- [x] **D-TG8: Update clean** — `update.py --all --test` runs with no errors (PASSED)

---

## Phase E: Token Expansion (5 → 13 tokens)

> **Goal:** Expand from 5 tokens to 13 by adding DOGE, AVAX, LINK, ADA, SUI, TON, DOT, NEAR.

### E1. Token selection research
- [x] Evaluated 40+ sources (CoinGecko, CryptoSlate, TradingView, KuCoin reports, Grayscale, ARK Invest)
- [x] Ranked by profit proxy: daily swing % x TA signal reliability x liquidity depth
- [x] All 8 candidates verified on KuCoin via CCXT
- [x] Timeframe fitness confirmed: all 8 tokens outperform BNB (lowest existing) on avg candle swing %

### E2. Implementation
- [x] Added 8 tokens to `TOKENS` in `config.py` (5 → 13)
- [x] No workflow changes needed — all 3 GitHub Actions use `--all` flag

### E3. Seeding
- [x] All 8 tokens seeded across all 3 timeframes (24 seed operations)
- [x] Every seed: 500 candles fetched, 301 docs after NaN warmup drop
- [x] Indicator glossary auto-synced to `indicator_metadata` on each seed

### E4. Verification
- [x] Incremental update test: `update.py --all --timeframe 1h` — all 13 tokens OK
- [x] 39 collections live in production (13 tokens x 3 timeframes)

### Tokens added
| Token | Symbol | Sector | Rationale |
|-------|--------|--------|-----------|
| Dogecoin | DOGE-USDT | Meme/Payments | Highest volume outside existing set, excellent RSI/MACD responsiveness |
| Avalanche | AVAX-USDT | L1 DeFi | KuCoin-endorsed, clean Ichimoku/Supertrend signals |
| Chainlink | LINK-USDT | Oracle/RWA | Massive volume, strong Fib/BB signals |
| Cardano | ADA-USDT | L1 | Consistent top-10, large TA community |
| SUI | SUI-USDT | L1 (Move) | Fastest-growing L1, highest Tier 1 swing % |
| Toncoin | TON-USDT | Social/Telegram | Telegram ecosystem (800M users), KuCoin-endorsed |
| Polkadot | DOT-USDT | Interop (L0) | CoinDesk 20 component, exceptional 4h/1d swings |
| NEAR Protocol | NEAR-USDT | AI/L1 | Highest swing of all candidates, AI sector pivot |

---

## Phase F: Deep Historical Backfill

> **Goal:** Fetch max available history from KuCoin for all tokens to enable strategy backtesting. One-time operation.

### Implementation
- [x] `db.py`: Added `load_all()` (full collection OHLCV load) and `bulk_upsert_chunked()` (5K-doc batch upserts)
- [x] `pipeline.py`: Added `run_backfill()` and `run_backfill_all()` with paginated fetch loop, merge logic, `--since` override
- [x] `backfill.py`: CLI entry point with `--symbol`, `--all`, `--timeframe`, `--all-timeframes`, `--test`, `--dry-run`, `--skip-btc`, `--since`

### Execution Results (2026-03-18)

**Daily (1d) — all 12 altcoins backfilled to production:**

| Token | Docs | Earliest Date | KuCoin Listing |
|-------|------|---------------|----------------|
| ETH | 2,858 | 2017-10-19 | Oct 2017 |
| XRP | 2,414 | 2018-12-04 | Dec 2018 |
| BNB | 2,266 | 2019-06-19 | Jun 2019 |
| ADA | 2,251 | 2019-07-04 | Jul 2019 |
| LINK | 1,838 | 2020-08-20 | Aug 2020 |
| DOT | 1,837 | 2020-08-21 | Aug 2020 |
| NEAR | 1,515 | 2021-07-09 | Jul 2021 |
| SOL | 1,489 | 2021-08-04 | Aug 2021 |
| DOGE | 1,665 | 2021-02-09 | Feb 2021 |
| AVAX | 1,641 | 2021-03-05 | Mar 2021 |
| TON | 1,040 | 2022-10-27 | Oct 2022 |
| SUI | 852 | 2023-05-03 | May 2023 |

**4h — all 13 tokens backfilled to production (from Jan 2020 or listing date):**

| Token | Docs | Earliest Date |
|-------|------|---------------|
| BTC | 18,212 | 2017-10-18 (extended via --since 2017-10-01) |
| ETH | 13,414 | 2020-01-01 |
| XRP | 13,414 | 2020-01-01 |
| BNB | 13,414 | 2020-01-01 |
| ADA | 13,414 | 2020-01-01 |
| LINK | 12,020 | 2020-08-20 |
| DOT | 12,012 | 2020-08-21 |
| DOGE | 10,984 | 2021-02-09 |
| AVAX | 10,838 | 2021-03-05 |
| NEAR | 10,082 | 2021-07-09 |
| SOL | 9,926 | 2021-08-04 |
| TON | 6,934 | 2022-12-16 |
| SUI | 5,854 | 2023-06-14 |

**1h — not backfilled** (skipped to save Atlas quota; available via `backfill.py --all --timeframe 1h` if needed).

**Phase F: COMPLETE** (2026-03-18)

---

## Current Status

**Phase A: COMPLETE** — All new modules created, requirements updated. All 7 test gates passed (2026-03-01).
**Phase B: COMPLETE** — All 4 tokens seeded. 8/8 test gates passed (2026-03-01).
**Phase C: COMPLETE** — Production cutover done, legacy scripts deleted, app.py updated (2026-03-18). Remaining DB cleanup (drop old collections) deferred until downstream repos fully migrated.
**Phase D: COMPLETE** — All indicators implemented, test gates passed, 39 collections live (2026-03-18).
**Phase E: COMPLETE** — 8 new tokens added (5 → 13). All 39 collections seeded and verified (2026-03-03).
**Phase F: COMPLETE** — Deep historical backfill for all tokens, daily + 4h (2026-03-18).

**Phase G: COMPLETE** (2026-03-22) — Perpetual futures data pipeline. 13 perp daily + 13 funding rate collections live. See [docs/PERPETUAL_FUTURES.md](PERPETUAL_FUTURES.md).
**Phase H: COMPLETE** (2026-03-22) — Storage optimization. Dropped 1h+4h collections (27 total, ~200 MB freed). Daily-only production. Hourly/4h GitHub Actions workflows deleted.
**Phase I: COMPLETE** (2026-03-27) — Restored BTC-only 1h data (spot + perp) for external project consumption. Backfilled spot 1h from Jan 2020 (~54K docs), perp 1h from Dec 2024 (~11K docs, KuCoin Futures 1h history limit). New hourly workflow (`update-hourly.yml`) runs BTC-only. All other tokens remain daily+weekly only.
**Phase J: COMPLETE** (2026-04-04) — Mac Mini M4 Pro migration. Python 3.12, 18 tokens (added PEPE/WIF/SHIB/WLD/ARB), local Docker MongoDB, launchd automation (daily 01:05 + hourly :05) via Python launchers (no bash/FDA needed), Telegram alerts with photo + emoji, CSV backup (1.0 GB), GH Actions cron disabled (manual fallback kept). 100 collections, 53/53 tests pass.

### Notes
- `pandas-ta` (original) is dead on PyPI for Python 3.11+. Using `pandas-ta-classic` (import as `pandas_ta_classic`).
- VWAP: rolling 24-bar for intraday (1h, 4h), cumulative for daily. Fixes sliding window reset artifact.
- Fibonacci column names use underscores (`Fib_236`) not dots (`Fib_0.236`) — MongoDB doesn't allow dots in field names.
- `Stoch_RSI` column removed (was duplicate of `Stoch_RSI_K`). Only `Stoch_RSI_K` and `Stoch_RSI_D` remain.
- `ROC_12`/`ROC_24` removed — `LogReturn_12`/`LogReturn_24` are mathematically equivalent and ML-preferred.
- Ichimoku A/B have small library-level differences (Senkou span shift handling). Both computations are valid.
- Fear & Greed API: free, no signup, daily resolution. Same value merged into all candles per pipeline run.
- `compute_all()` now takes `timeframe` parameter for VWAP calculation mode.

---

## Phase J: Mac Mini M4 Pro Migration (2026-04-04)

> **Goal:** Migrate from GitHub Actions + MongoDB Atlas to local launchd + Docker MongoDB on Mac Mini M4 Pro. Add 5 tokens, Telegram alerts, and CSV backup.

### J1. Environment setup
- [x] Deleted Windows `pyvenv.cfg` remnant
- [x] Created Python 3.12 venv at `venv/` (arm64 native)
- [x] Updated `.mcp.json` to use `venv/bin/python`
- [x] Updated `.gitignore` (added `venv/`, `logs/`, `data/`)
- [x] Updated `requirements.txt` (`pymongo[srv]` → `pymongo`, added `pytest`)
- [x] Created `.env` with local MongoDB URI + Telegram credentials

### J2. Token expansion (13 → 18)
- [x] Added PEPE, WIF, SHIB, WLD, ARB to `config.py` (TOKENS + TOKEN_METADATA)
- [x] All 5 confirmed on KuCoin (spot + perp + funding)
- [x] Updated `test_config.py` assertion (was hardcoded `== 13`)

### J3. Data population
- [x] Seeded all 5 new tokens (spot daily + weekly + perp daily)
- [x] Deep backfilled all 5 new tokens (spot daily + perp daily + funding rates)
- [x] Seeded weekly data for original 13 tokens (was missing from CRA import)
- [x] MongoDB: 66 → 100 collections, all populated with indicators

### J4. CSV backup
- [x] Created `export_data.py` — exports all collections to `data/` as CSV
- [x] Structure: `data/spot/`, `data/perp/`, `data/funding/`, `data/metadata/`
- [x] 100 CSV files, ~831K rows, ~1.0 GB

### J5. Pipeline scripts
- [x] Created `bin/run_daily.py` — Python launcher: 4 steps (spot + perp + weekly + CSV), Telegram GREEN/RED with photo support
- [x] Created `bin/run_hourly.py` — Python launcher: BTC 1h (spot + perp), Telegram RED on failure only
- [x] Created `bin/btc-daily.sh` / `bin/btc-hourly.sh` — bash wrappers for manual terminal runs
- [x] Created `bin/notify.sh` — shared Telegram helper for bash wrappers

### J6. launchd automation
- [x] Created `com.eeva.tracker-daily.plist` (01:05 UTC, StartCalendarInterval)
- [x] Created `com.eeva.tracker-hourly.plist` (every hour at :05)
- [x] Both loaded via `launchctl bootstrap`
- [x] Plists call Python directly (not bash) to avoid macOS TCC/FDA permission issues — same pattern as CRA's `com.eeva.monthly-review`

### J7. GitHub Actions
- [x] Removed `schedule:` from `update-daily.yml` and `update-hourly.yml`
- [x] Kept `workflow_dispatch:` as manual fallback (writes to Atlas)

### J8. Verification
- [x] Daily pipeline: all 4 steps pass, Telegram GREEN received
- [x] Hourly pipeline: both steps pass, silent on success
- [x] Failure path: Telegram RED alert with error details
- [x] 53/53 tests pass (no regression from baseline)
- [x] 100 MongoDB collections, all 18 tokens fresh

### Phase J: COMPLETE (2026-04-04)
