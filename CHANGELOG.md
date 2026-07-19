# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Every write stored an in-progress candle and froze it (2026-07-19).** `run_update` used `_floor_timestamp(now)` — the start of the candle currently *forming* — as the fetch-window bound and never filtered the fetched rows, so each run wrote a partial candle. The next run's gap check saw that timestamp as already stored and skipped it, so it was never corrected. **Measured against KuCoin's own candles (BTC daily, 291 bars): 76% of the 112 bars since the 2026-03-29 DST change have a wrong Close (mean 19.3 bps, max 143 bps) and 12% miss the true high or low** — 2026-07-16 stored Low 63,859.2 against a true 63,750.0, the day's actual low having fallen in the final 50 minutes. The 1h collections were worse: the hourly job runs at :05, so each hourly bar was frozen with ~5 minutes of trading in it (verified live — the stored "latest" 1h row was always the forming hour). The seasonal split is the mechanism: launchd fires on **machine local** time, so the daily job's 01:10 slot is 00:10 UTC under CET (writes the completed previous day, correct) but 23:10 UTC under CEST (writes the open current day). New `_last_closed_period()` / `_drop_unclosed()`; `run_update` and `run_perp_update` now bound the fetch window by the last *closed* period and filter the fetched frame as well (an exchange may return a candle we did not ask for). Affects all timeframes — the root cause was shared code, not daily-specific. +16 tests (74 → 90).

### Added
- **`--refresh-last N` on `update.py`** — also re-fetch and overwrite the most recent N **closed** candles even though they are already stored. The gap check only ever looks at the newest stored timestamp, so a candle the exchange later revises could never be noticed. Wired as `--refresh-last 2` into `bin/run_daily.py` and `bin/run_hourly.py`: a rolling two-period self-heal that also repairs the hand-over (the last partial bar written by the old code is already stored, so the gap check alone would freeze it wrong forever). Older history is untouched — see the note on backfill below.
- **`bin/run_hourly.py` now also closes the daily and weekly bars.** `run_update` returns before fetching unless a new period has closed, so on 23 of 24 runs these steps are a no-op. What they buy is schedule independence: the completed daily bar now lands at **00:05 UTC year-round**, regardless of what local hour the daily job happens to fire at under DST.
- **`deploy/com.eeva.tracker-{daily,hourly,watchdog}.plist` captured into version control.** These existed only as real files in `~/Library/LaunchAgents/` with no source of truth. `tracker-daily` Hour changed 1 → 3 (01:10 local was 23:10 UTC under CEST; any local hour 02:10-22:00 is past the UTC boundary in both regimes). Correctness no longer depends on this — it is a freshness change. **Not installed** — install instructions are in each plist header.

### Known issue (not fixed)
- **Historical rows remain truncated.** Fix-forward only, by decision: correcting stored history means rewriting `{token}_{tf}_price_data`, the shared contract collection every repo reads, and would invalidate every metric already computed from it. Note `backfill.py` **cannot** do this repair — its merge is `pd.concat([df_exchange, df_existing])` with `keep="last"` (`pipeline.py:311-317`, `:641-647`), so already-stored data always wins on a timestamp collision; it fills gaps but never corrects a row. A real repair must also recompute indicators forward ≥ `SLIDING_WINDOW` (200) periods, and daily/weekly `VWAP` is a `cumsum` over all prior rows.

## [0.2.0] — 2026-04-26

### Fixed
- **Funding rate silent staleness (KuCoin ~2-day API dead zone).** `run_perp_update` derived the funding fetch `since_ms` from the OHLCV candle gap (= yesterday). KuCoin's `fetch_funding_rate_history` silently returns 0 records when `since >= (now − 2d)`, so funding data stopped accumulating after the initial seed. Root consequence: `funding_rate_ma_7d` went NaN after 7 days and CRA defaulted regime to BEAR, masking the real market signal. Fix: `_get_funding_since_ms()` looks up the last stored funding timestamp from MongoDB and subtracts a 3-day buffer, always landing outside the dead zone. Upsert idempotency absorbs the daily overlap. Manual backfill executed 2026-04-26 (27–54 records per token, 9-day gap closed). 9 new tests.
- **`_fetch_and_store_funding` silent empty result.** Previously logged nothing when the API returned 0 records, making the bug invisible in daily logs. Now logs `No new funding rate records (KuCoin returned empty)`.

### Added
- **Watchdog covers funding_rate collections.** `run_watchdog.py` now checks all 18 `{token}_funding_rate_data` collections with a 36h threshold (same as daily OHLCV). Previously the watchdog only checked 72 OHLCV collections and reported GREEN while funding data was 9 days stale. Checked total is now 90.

## [0.1.0] — 2026-04-19

### Added
- Initial repository scaffolding via `/cms init`.
