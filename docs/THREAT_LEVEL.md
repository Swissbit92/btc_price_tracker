---
title: Threat Level
status: active
created: 2026-08-09
last_reviewed_on: 2026-08-09
review_in: 6 months
applies_to: btc_price_tracker
threat_level: Medium
---

# Threat Level: Medium

**Medium.** Lower than `eeva-exec` and `Crypto_Research_Assistant`, and the gap
is real rather than a rounding-down: this repo holds no credential that can
reach an account, and the path from a compromise here to lost capital runs
through CRA's verdict gates and a manual promotion step.

It is not Low, because it owns the data that every downstream decision is fitted
to, and nothing downstream checks it.

## What a compromise could do

- **Write plausible-but-wrong candles.** The dangerous version is not obvious
  corruption — a zeroed Close breaks loudly. It is a Close shifted by a few
  tenths of a percent, which produces strategies that backtest well and lose
  money, and survives every existing check.
- **Poison funding rates.** Carry entry and the BULL regime gate are both
  functions of funding. Falsified funding could open carry positions that never
  clear breakeven, or hold the directional sleeve on through a regime it should
  have stood down in.
- **Stop silently.** The watchdog covers this — 36h for daily, 3h for hourly —
  which is why staleness is a managed risk rather than an open one.
- **Delete history.** Recovery means re-running `seed.py` and `backfill.py` over
  years of candles. Expensive, and see below for why partial corruption is worse.

## What it could not do

- Place an order or read a balance. No exchange credential exists here.
- Write `strategy_signals` — that is CRA's contract.
- Reach any KuCoin account, sub-account or wallet.

## The risk that is not an attacker

This repo's realistic failure mode has no adversary in it, and it has already
happened:

1. **The truncated-close bug (pre-2026-07-19).** `run_update` stored the
   currently-forming candle, and the gap check then skipped it forever. **76% of
   daily Closes since the 2026-03-29 DST change were wrong.** Every downstream
   consumer accepted them. No test failed. This is the canonical example of the
   whole category.
2. **`backfill.py` cannot repair it.** The merge keeps existing rows on
   collision, so the naive repair is a no-op. Pre-2026-07-19 history remains
   truncated and the repair decision is still open in
   [ROADMAP.md](ROADMAP.md).
3. **launchd fires in machine-local time.** The daily job ran at 01:10 local,
   which was 00:10 UTC under CET but 23:10 UTC under CEST — the wrong side of the
   UTC day boundary for half the year. Moved to 03:10 on 2026-07-19.
4. **Interpreter drift.** Python 3.12 must match in four places (local venv, both
   workflows, Dockerfile). They diverged once, so the Atlas fallback would have
   run a different interpreter than production precisely when production was
   already broken.

Every item on that list wrote or would have written wrong data while looking
entirely healthy. That is what the Medium rating is about.

## Explicitly accepted

- **No verification of exchange data.** Candles are taken as KuCoin reports them.
  A second source to cross-check against would mean two ingestion paths that can
  disagree, and reconciling them is a larger problem than the one it solves at
  this scale.
- **MongoDB unauthenticated on localhost.** Same posture as every sibling repo;
  the host is the boundary.
- **Read-only MCP server exposed to agents.** It queries, it never writes. The
  read-only property is the control, and it is worth keeping structural rather
  than conventional.
- **Truncated pre-2026-07-19 history left in place.** A known-wrong dataset that
  is documented rather than repaired. Acceptable only because it *is* documented —
  the danger is a future analysis that forgets.

## What would raise this to High

Adding an authenticated exchange key for any reason, or MongoDB becoming
reachable off-host. The first would give this repo an account to lose; the second
would remove the only boundary currently doing the work.
