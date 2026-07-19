---
title: Lessons Learned
status: active
created: 2026-04-19
last_reviewed_on: 2026-05-30
review_in: 12 months
applies_to: btc_price_tracker
---

# Lessons Learned

Append-only, dated entries. Newest first. Each entry: what happened, what we learned, how to apply going forward.

## 2026-07-19 — Every candle we ever wrote was a partial one, and the gap check guaranteed it stayed that way

- **What:** `run_update` bounded its fetch window with `_floor_timestamp(now)` — the start of the candle currently *forming*, not the last one that closed — and never filtered the rows CCXT returned. So every run stored an in-progress candle. The next run's gap check then saw that timestamp as already present and skipped it, so the partial value was frozen permanently. Measured against KuCoin's own candles (BTC daily, 291 bars): **76% of the 112 bars since the 2026-03-29 DST change have a wrong Close** (mean 19.3 bps) and 12% miss the true high or low — 2026-07-16 stored a Low of 63,859.2 against a true 63,750.0, because the day's actual low fell in the final 50 minutes. The 1h collections were worse: the hourly job runs at :05, so each hourly bar held roughly five minutes of trading. Found while investigating an unrelated CRA question about funding-settlement timing.
- **Learned:** (1) **The seasonal split was the whole diagnosis.** Winter bars were mostly fine and summer bars mostly wrong, which pointed straight at launchd firing on *machine local* time: 01:10 is 00:10 UTC under CET (writes the completed previous day) but 23:10 UTC under CEST (writes the open current day). A defect with a 14%/76% split by date range is telling you where to look. (2) **An incremental "have I got this timestamp?" check cannot self-heal by construction** — it can only ever notice absence, never wrongness. Any pipeline built that way needs an explicit refresh window. (3) **`backfill.py` looked like the repair tool and is not**: its merge is `pd.concat([df_exchange, df_existing])` with `keep="last"`, so stored data always wins a collision. It fills gaps and silently preserves bad rows. Do not assume a backfill script can correct. (4) **ObjectId prefixes encode insert time** (`datetime.fromtimestamp(int(oid[:8], 16))`) — that is how the 23:10 write time was proven with no logging at all. Caveat: a bulk re-ingest shares one prefix, so it reveals nothing about the live schedule.
- **Apply:** Never write a candle whose period has not closed — bound the fetch window by the last *closed* period and filter the fetched frame too, since an exchange may return candles you did not ask for. Give every incremental pipeline a small rolling refresh window (`--refresh-last N`) so revisions and hand-over rows can heal. Prefer making correctness independent of the schedule (the hourly job now closes the daily bar at 00:05 UTC year-round) over getting a local-time cron right, because DST will move it twice a year. When a job's correctness depends on a UTC boundary, assert that in a test with an explicit `now`, not in a comment.

## 2026-04-26 — KuCoin funding rate API has a ~2-day silent dead zone

- **What:** `btc_funding_rate_data` (and all 17 other token funding collections) stopped updating silently after the initial seed on 2026-04-17. The daily pipeline called `_fetch_and_store_funding` with `since_ms` derived from the OHLCV candle gap (= yesterday). KuCoin's `fetch_funding_rate_history` silently returns 0 records when `since >= (now − 2d)` — no error, no warning, just an empty response. The function also had no log line for the empty case, making the failure invisible in daily logs. After 7 days the 7-day funding MA went NaN, and CRA's `emit-signals` defaulted regime to BEAR. The watchdog also had no visibility because it only checked the 72 OHLCV collections, not the 18 funding_rate collections.
- **Learned:** (1) Silently empty API responses are a distinct failure class from errors — both `_fetch_and_store_funding` and the watchdog must cover them. (2) Any `since_ms` derived from a recent gap will fall in the dead zone; always anchor to the last stored MongoDB timestamp and subtract a safety buffer (3 days used here). (3) Watchdog coverage must mirror the full set of collections that downstream consumers depend on — omitting funding_rate from the watchdog was the reason this went 9 days undetected despite daily GREEN Telegram messages.
- **Apply:** When adding any new data collection to this pipeline, immediately add it to `run_watchdog.py`'s `check_freshness`. When fetching paginated history from any exchange API, anchor `since_ms` to the last stored document, not to a derived gap date. Log explicitly when an incremental fetch returns empty.

## 2026-04-19 — Repository initialized

- **What:** `/cms init` scaffolded the standard doc set.
- **Learned:** Creation-time enforcement is the strongest lever for doc hygiene (Nx, Kubernetes OWNERS, Backstage).
- **Apply:** Any new repo starts here. Retroactive audits drift; creation-time templates don't.
