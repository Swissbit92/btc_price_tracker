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

## Freshness is measured in whole periods, never in wall-clock age

Status: active
Check: tools/checks/freshness_is_period_based.sh

WHEN a check decides whether stored data is stale THE SYSTEM SHALL compare against
`_last_closed_period(now, timeframe)` — via `periods_behind` — and SHALL NOT compare
`now - timestamp` to a fixed duration.

A bar is stamped at the *start* of a period that closes one period later, so its timestamp
age oscillates by a full period between writes: daily 25h→49h, weekly 7→14 days. Any
wall-clock threshold is therefore correct only at one hour of the day. The 36h daily bound
passed solely because the job runs at 05:00 UTC; run at 21:28 UTC against healthy data it
reported 34 collections stale and fired a RED alert with nothing wrong.

The monitoring code must import that boundary function rather than reimplement it. Two
independent notions of "when did a period close" is exactly the defect that stalled weekly
updates for three weeks.

Funding rates are the deliberate exception: an 8h period against a 36h bound absorbs the
oscillation, and the failure it guards is a silent API dead zone, not boundary alignment.

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

## compute_all must never raise, whatever the series length

Status: active
Check: tools/checks/compute_all_survives_short_series.sh

WHEN `compute_all` is given an OHLCV frame of any length THE SYSTEM SHALL return a frame,
leaving columns it cannot compute absent or NaN, and SHALL NOT raise.

Two separate crashes shipped here because `pandas_ta` signals "not enough history" by
returning `None` rather than an empty frame, and the calling code assumed a frame. Guarding
the container instead of the object (`ta.ichimoku` returns a *tuple* whose first element is
None) took out `compute_all` for any series under 52 periods; assigning a bare `None` to a
column produced an object dtype that later arithmetic could not subtract, crashing every
frame of 4-13 rows.

The consequence in both cases was total and silent: the token's update died, so no bar was
ever written, and five weekly collections sat stuck for up to 129 days while the logs showed
only pandas_ta's own "Returning None" notice.

NaN is the correct output for an indicator without enough history — it is what the write path
already treats as warmup. An exception is not.

## Warmup NaNs must not drop a bar

Status: active
Check: tools/checks/warmup_nans_do_not_drop_bars.sh

WHEN a row is considered for writing THE SYSTEM SHALL block it only for a NaN at or after
that column's first valid index, and SHALL write rows whose NaNs are indicator warmup.

`run_update` writes per timestamp and the gap check reads only the newest stored one, so a
dropped row is not deferred — it becomes permanently unreachable. Dropping on any NaN turned
six of SUI's seven pending weekly bars into holes and wrote the seventh, which is why sol's
series reads `04-02 -> 05-14 -> 06-18 -> 07-16`.

Warmup nulls are the documented contract, not a defect: `docs/ARCHITECTURE.md` states newer
tokens carry null SMA_200/EMA_200 until they have the history. A NaN *after* a column has
produced a value is a different thing entirely and still blocks.
