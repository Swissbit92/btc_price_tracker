# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-04-26

### Fixed
- **Funding rate silent staleness (KuCoin ~2-day API dead zone).** `run_perp_update` derived the funding fetch `since_ms` from the OHLCV candle gap (= yesterday). KuCoin's `fetch_funding_rate_history` silently returns 0 records when `since >= (now − 2d)`, so funding data stopped accumulating after the initial seed. Root consequence: `funding_rate_ma_7d` went NaN after 7 days and CRA defaulted regime to BEAR, masking the real market signal. Fix: `_get_funding_since_ms()` looks up the last stored funding timestamp from MongoDB and subtracts a 3-day buffer, always landing outside the dead zone. Upsert idempotency absorbs the daily overlap. Manual backfill executed 2026-04-26 (27–54 records per token, 9-day gap closed). 9 new tests.
- **`_fetch_and_store_funding` silent empty result.** Previously logged nothing when the API returned 0 records, making the bug invisible in daily logs. Now logs `No new funding rate records (KuCoin returned empty)`.

### Added
- **Watchdog covers funding_rate collections.** `run_watchdog.py` now checks all 18 `{token}_funding_rate_data` collections with a 36h threshold (same as daily OHLCV). Previously the watchdog only checked 72 OHLCV collections and reported GREEN while funding data was 9 days stale. Checked total is now 90.

## [0.1.0] — 2026-04-19

### Added
- Initial repository scaffolding via `/cms init`.
