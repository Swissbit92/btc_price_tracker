# Invariants

Standing constraints that bind **all** work in this repo, as opposed to a spec, which
describes one change and stops mattering once it ships.

No review dates: a constraint does not expire because nobody looked at it. Retiring one is a
decision — set `Status: retired`, leave the entry in place, and say why.

---

## Weekly candle boundaries are epoch-anchored, never weekday-anchored

Status: active
Check: tools/checks/weekly_epoch_anchor.sh

WHEN any function returns a `1w` candle boundary THE SYSTEM SHALL return a timestamp
satisfying `ts % 604800 == 0` (Thursday 00:00 UTC).

KuCoin buckets weekly candles by epoch modulo and the Unix epoch was a Thursday. ccxt passes
venue boundaries through unchanged and [deliberately never re-cuts them](https://github.com/ccxt/ccxt/issues/25046),
so every stored weekly bar carries the exchange's own anchor. Binance and TradingView use
Monday; that convention is not ours to assume.

Hardcoding Monday here stalled every weekly update for three weeks in 2026, and the test
written alongside the bug asserted the wrong weekday, so a green suite confirmed the defect.
The check therefore asserts the *invariant* over a date sweep rather than a weekday looked up
once — a weekday can be wrong, epoch alignment cannot drift.

## Never write a candle whose period has not closed

Status: active
Check: tools/checks/no_unclosed_candles.sh

WHEN the pipeline writes a candle THE SYSTEM SHALL bound the fetch window by the last *closed*
period AND filter the fetched frame, since an exchange may return candles that were not asked
for.

Storing an in-progress bar freezes it: the next run's gap check sees the timestamp as already
present and never revisits it. This produced wrong Closes on 76% of BTC daily bars over one
DST season. Correctness must not depend on what local hour a launchd job fires at.

## Collection names and indicator columns are a public API

Status: active
Check: none yet

WHEN a `{token}_{tf}_price_data` collection name or an indicator column name changes THE
SYSTEM SHALL require a coordinated cross-repo update first.

CRA and eeva-exec read these directly; there are no code imports between repos, so these
names *are* the interface. Governed ecosystem-wide by
[ADR-001](../../docs/decisions/001-indicator-columns-as-public-api.md) and
[ADR-004](../../docs/decisions/004-collection-naming-contract.md).

No check is wired, and that is an honest gap rather than an oversight: a rename is only a
violation in the absence of the corresponding downstream change, which nothing in this repo
can see. Enforcement is the ADR and review, not a script.
