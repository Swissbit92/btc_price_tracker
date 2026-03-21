# Perpetual Futures Data Pipeline (Phase G)

> Data contract: `Crypto_Research_Assistant/docs/PERPETUAL_DATA_SPEC.md`

## Overview

Extending `btc_price_tracker` to fetch perpetual futures OHLCV + funding rate data from KuCoin Futures via CCXT, compute indicators on perp price series, and store results in MongoDB. This unlocks short-selling and funding rate-aware PnL in the Crypto_Research_Assistant backtester.

**Motivation:** Long-only strategies ceiling at ~39% positive months. Adding perps + shorts targets ~50-55%.

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| CCXT class | `ccxt.kucoinfutures` | NOT `ccxt.kucoin` with swap options — KuCoin requires separate class |
| Module design | Separate `extract_perp.py` | Don't modify stable `extract.py` |
| Pipeline functions | Separate `run_perp_*()` in `pipeline.py` | Don't branch existing spot functions |
| Entry points | `--market-type` flag on existing CLIs | Standard pattern, thin dispatcher |
| Funding alignment | `period_start`-based matching | KuCoin's fundingTimestamp = END of previous round |
| Settlement intervals | Variable (8h/4h/1h) | Don't hardcode 3-per-day |
| Token scope | All 13 tokens | Build once |
| Data source | KuCoin Futures only (v1) | Reuse existing CCXT infra |
| OI / mark price OHLCV | Skip for v1 | KuCoin has no OI history via CCXT |

## New MongoDB Collections

| Pattern | Example | Count |
|---------|---------|-------|
| `{token}_perp_{timeframe}_price_data` | `btc_perp_daily_price_data` | 39 (13 tokens x 3 timeframes) |
| `{token}_funding_rate_data` | `btc_funding_rate_data` | 13 |
| `funding_rate_metadata` | (single collection) | 1 |

## Progress

| Phase | Status | Date | Agent | Notes |
|-------|--------|------|-------|-------|
| 0: Tracking doc | COMPLETE | 2026-03-21 | — | This file + MIGRATION.md reference |
| 1: Config layer | COMPLETE | 2026-03-21 | Config | PERP_SYMBOL_MAP, MARKET_TYPES, FUNDING_METADATA_COLLECTION, get_collection_name(market_type), get_funding_collection_name() |
| 2: extract_perp.py | COMPLETE | 2026-03-21 | Extract | kucoinfutures singleton, OHLCV + funding fetch. QA: rejected once (interval_hours hardcode, load_funding_rates missing sort/conversion), fixed and re-passed. |
| 3: db.py extensions | COMPLETE | 2026-03-21 | Database | market_type routing on 7 functions, 5 new funding CRUD functions. QA: passed after fixes. |
| 4: Pipeline functions | COMPLETE | 2026-03-21 | Pipeline | _align_funding_to_candles (period_start-based), _merge_perp_funding, _fetch_and_store_funding, run_perp_seed/update/backfill + _all variants. QA: passed. |
| 5: Indicators glossary | COMPLETE | 2026-03-21 | Pipeline | Funding_Rate, Mark_Price, Basis_Pct added to INDICATOR_GLOSSARY (Derivatives category). Excluded from NaN validation. compute_all() untouched. QA: passed. |
| 6: CLI --market-type | COMPLETE | 2026-03-21 | CLI+CI | --market-type flag on seed.py, update.py, backfill.py. Lazy imports, full arg passthrough. QA: passed. |
| 7: GitHub Actions | COMPLETE | 2026-03-21 | CLI+CI | Perp step added after spot in all 3 workflows. QA: passed. |
| 8: MCP server | COMPLETE | 2026-03-21 | MCP | market_type param on 4 tools, list_collections returns 91 entries, new query_funding_rates tool. QA: passed. |
| 9: Unit tests | COMPLETE | 2026-03-21 | Tests | 64 tests across 4 files. QA: rejected once (fragile `is None` assertions, missing fallback test), fixed and re-passed. Tests also found+fixed a timezone bug in _align_funding_to_candles. |
| 10: Metadata seeding | COMPLETE | 2026-03-21 | Metadata | seed_funding_metadata() + _KUCOIN_CONTRACT_MAP (13 tokens, BTC=XBTUSDTM). QA: passed. |
| Test DB validation | COMPLETE | 2026-03-21 | QA | Gates 1-6 passed. Found KuCoin Futures 200-candle/request limit (fixed). Gate 7 (full backfill) deferred — pipeline proven via dry run. |
| Production deploy | PENDING | | QA | Ready after full backfill |

## Architecture Decisions

*(Recorded as phases complete)*

## Findings Log

- **2026-03-21 (Phase 2 QA):** CCXT normalizes KuCoin's `XBT` ticker to `BTC` internally via `commonCurrencies`. `BTC/USDT:USDT` is the correct unified symbol — `XBT/USDT:USDT` raises `BadSymbol`. No special-casing needed.
- **2026-03-21 (Phase 2 QA):** KuCoin funding rate `interval_hours` cannot be assumed to be 8 for all tokens/periods. Must derive from consecutive records. Single-record case returns `None`.
- **2026-03-21 (Phase 3 QA):** `period_start` stored as UTC datetime in MongoDB must be explicitly converted with `pd.to_datetime(..., utc=True)` when loaded back, otherwise timezone-aware comparisons fail silently.
- **2026-03-21 (Phase 9):** Tests found a pandas 2.x timezone-stripping bug in `_align_funding_to_candles`: `.values` on a UTC-aware Series produces timezone-naive `datetime64[ns]`. Fixed by using Series directly instead of `.values`.
- **2026-03-21 (Phase 9 QA):** Never use `is None` to check pandas cell values — use `pd.isna()`. Single-element DataFrames may preserve `None` as `object` dtype (fragile coincidence), but multi-element DataFrames convert to `NaN`.
- **2026-03-21 (Gate 3):** KuCoin Futures returns max **200 candles per request** (not 500 like spot). Fixed batch_size in extract_perp.py from 500 to 200. Pagination works correctly after fix.
- **2026-03-21 (Gate 3):** KuCoin funding rate response does NOT include `markPrice` or `indexPrice` — both are `None`. `basis_pct` will always be `None`. This is a KuCoin API limitation; Binance would provide these fields.
- **2026-03-21 (Gate 6):** BTC perp daily: 2,183 candles available from 2020-03-30 to present. 5,049 funding rate records available.

## Verification Results

*(Results from each test gate)*

## Collections Created

*(List of new MongoDB collections with doc counts and date ranges)*

---

*Started: 2026-03-21*
*Status: In Progress*
