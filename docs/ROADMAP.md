---
title: Roadmap
status: active
created: 2026-04-19
last_reviewed_on: 2026-05-30
review_in: 3 months
applies_to: btc_price_tracker
---

# Roadmap

Near-term dated items only. Strategic direction lives in the ecosystem [VISION.md](../../VISION.md).

## Next (this month)

- [ ] **DECISION: backfill the historically truncated OHLCV bars.** Every bar written before
      2026-07-19 is a partial candle — the pipeline stored the *currently forming* candle and
      the gap check then skipped it forever. Measured against KuCoin's own candles (BTC daily,
      291 bars): **76% of the 112 bars since the 2026-03-29 DST change have a wrong Close**
      (mean 19.3 bps, max 143 bps) and 12% miss the true high or low. Winter bars are mostly
      fine (14% wrong) because 01:10 CET is 00:10 UTC; summer bars are not, because 01:10 CEST
      is 23:10 UTC.

      **Fixed forward** (see CHANGELOG 2026-07-19) — new bars are correct and `--refresh-last 2`
      self-heals the last two periods. **History was deliberately left alone**, and that is now
      the open item, because *every backtest number in the ecosystem rests on these bars* —
      including CRA's deployed `portfolio_deployed.json` figures (CMII 59.4%, max DD 5.7%),
      which were themselves corrected on 2026-07-19 but computed from uncorrected prices.

      **This is not a cleanup — it is an R10 decision.** Rewriting `{token}_{tf}_price_data`
      touches the shared contract collection every repo reads, and invalidates every stored
      metric derived from it.

      Non-obvious constraints, established 2026-07-19:
      - **`backfill.py` CANNOT do this.** Its merge is `pd.concat([df_exchange, df_existing])`
        with `keep="last"` (`pipeline.py:311-317`, `:641-647`) — already-stored data always wins
        a timestamp collision. It fills gaps; it never corrects a row.
      - A repair must **recompute indicators forward** at least `SLIDING_WINDOW` (200) periods
        from each corrected bar, because SMA_200/EMA_200 and the 50-period risk metrics read
        backwards.
      - Daily/weekly **`VWAP` is a `cumsum`** over all prior rows (`indicators.py:988-992`), so
        a strict full recompute changes every subsequent bar. Note the *stored* VWAP is already
        only a ~200-bar approximation, because `run_update` recomputes on a sliding window — a
        full-history repair would produce truer but *inconsistent* values.
      - The write path itself is safe: `UpdateOne(upsert=True)` keyed on a floored `timestamp`
        (`db.py:76-92`), single unique index, so re-writing a day cleanly overwrites.

      Scope options, cheapest first: (a) leave history, treat pre-2026-07-19 data as
      approximate and document it; (b) repair the CEST window only (~112 bars/token); (c) full
      history repair + forward indicator recompute.

## Soon (next quarter)

- [ ] TBD

## Later (exploratory)

- [ ] TBD

## Shipped

See [CHANGELOG.md](../CHANGELOG.md).
