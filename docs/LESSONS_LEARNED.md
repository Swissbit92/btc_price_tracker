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

## 2026-04-26 — KuCoin funding rate API has a ~2-day silent dead zone

- **What:** `btc_funding_rate_data` (and all 17 other token funding collections) stopped updating silently after the initial seed on 2026-04-17. The daily pipeline called `_fetch_and_store_funding` with `since_ms` derived from the OHLCV candle gap (= yesterday). KuCoin's `fetch_funding_rate_history` silently returns 0 records when `since >= (now − 2d)` — no error, no warning, just an empty response. The function also had no log line for the empty case, making the failure invisible in daily logs. After 7 days the 7-day funding MA went NaN, and CRA's `emit-signals` defaulted regime to BEAR. The watchdog also had no visibility because it only checked the 72 OHLCV collections, not the 18 funding_rate collections.
- **Learned:** (1) Silently empty API responses are a distinct failure class from errors — both `_fetch_and_store_funding` and the watchdog must cover them. (2) Any `since_ms` derived from a recent gap will fall in the dead zone; always anchor to the last stored MongoDB timestamp and subtract a safety buffer (3 days used here). (3) Watchdog coverage must mirror the full set of collections that downstream consumers depend on — omitting funding_rate from the watchdog was the reason this went 9 days undetected despite daily GREEN Telegram messages.
- **Apply:** When adding any new data collection to this pipeline, immediately add it to `run_watchdog.py`'s `check_freshness`. When fetching paginated history from any exchange API, anchor `since_ms` to the last stored document, not to a derived gap date. Log explicitly when an incremental fetch returns empty.

## 2026-04-19 — Repository initialized

- **What:** `/cms init` scaffolded the standard doc set.
- **Learned:** Creation-time enforcement is the strongest lever for doc hygiene (Nx, Kubernetes OWNERS, Backstage).
- **Apply:** Any new repo starts here. Retroactive audits drift; creation-time templates don't.
