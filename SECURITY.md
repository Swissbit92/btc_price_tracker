# Security

## There is nothing here worth stealing

This repo holds **no exchange credential**. CCXT talks to KuCoin's public
endpoints; no API key, secret or passphrase exists in the code or the
environment. It cannot place an order, cannot read a balance, and cannot reach an
account.

What it has instead is write access to the collection every other repo believes.

## Secret handling

| Secret | Where it lives | If it leaks |
|---|---|---|
| `MONGODB_URI` | `.env` (gitignored) | Write access to the price contract. The only one that matters. |
| `TG_BOT_TOKEN` / `TG_CHAT_ID` | `.env` | Messages to one chat. |

That is the whole list. A short credential list is the strongest security
property this repo has, and it is worth keeping short — adding an authenticated
exchange key here to fetch something convenient would change the repo's category.

## The real asset: the data contract

`{token}_{tf}_price_data` and the funding-rate collections are consumed by CRA
(strategy discovery and backtests) and, through CRA's signals, by `eeva-exec`
(real orders). Nothing downstream re-derives or verifies these candles.

So the integrity chain runs:

> corrupt candles → strategies fitted to fiction → signals emitted on that basis
> → real trades

Two hops, no adversary required at any step. **This is not hypothetical**: the
pre-2026-07-19 truncated-close bug wrote the *forming* candle instead of the
closed one, and 76% of daily Closes were wrong for months. Nothing detected it,
because wrong-but-plausible numbers are indistinguishable from right ones
downstream.

The controls that matter are therefore correctness controls, not access controls:

- Only closed candles are written — `run_update` bounds its window by
  `_last_closed_period()`.
- `--refresh-last N` re-fetches recent closed candles so revisions self-heal.
- The watchdog checks freshness across 85 collections daily.
- Column names are a public API ([ADR-001](../docs/decisions/001-indicator-columns-as-public-api.md))
  and collection naming is a shared contract
  ([ADR-004](../docs/decisions/004-collection-naming-contract.md)). Renaming one
  is a cross-repo change, not a local edit.

## Naming the sharp edge

`backfill.py` **cannot repair corrupted history** — its merge keeps the existing
row on a collision. Anything already written wrong stays wrong until it is
explicitly deleted first. This is a data-integrity trap, not a security hole, but
it is the reason a corruption event here is expensive to undo rather than merely
annoying.

## Deliberately not built

- **MongoDB authentication.** Local Docker, not exposed off-host. The boundary
  doing the work is the host.
- **Checksums or signatures on written candles.** They would detect tampering but
  not the failure mode that actually occurred, which wrote *authentic* data from
  the wrong point in time. Correct-by-construction beat verification here.
- **An authenticated exchange connection.** Public endpoints are sufficient for
  OHLCV and funding. Adding a key for convenience would give this repo an account
  to lose.

## Reporting

Private repo, single operator. Anything found here goes straight to the
operator — there is no external disclosure process.
