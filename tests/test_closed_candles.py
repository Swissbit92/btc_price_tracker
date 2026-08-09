"""Only closed candles may be written (2026-07-19).

`_floor_timestamp` returns the start of the candle currently FORMING. `run_update`
used it as the upper bound of the fetch window and never filtered the fetched rows,
so every run stored a partial candle and then never revisited it — the next run's
gap check saw the timestamp as already present.

Measured damage before the fix, BTC daily vs KuCoin's own candles: 76% of the 112
bars since the 2026-03-29 DST change had a wrong Close (mean 19.3 bps) and 12%
missed the true high or low. 2026-07-16 stored Low 63,859.2 against a true 63,750.0
— the day's actual low fell in the final 50 minutes. The 1h collections had it
worse: the hourly job runs at :05, so each hourly bar was frozen with roughly five
minutes of trading in it.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from btc_tracker_mongodb.pipeline import (
    periods_behind,
    _drop_unclosed,
    _floor_timestamp,
    _last_closed_period,
)


class TestLastClosedPeriod:
    @pytest.mark.parametrize(
        "timeframe,now,expected",
        [
            ("1d", datetime(2026, 7, 18, 23, 10, tzinfo=timezone.utc), datetime(2026, 7, 17, tzinfo=timezone.utc)),
            ("1d", datetime(2026, 7, 19, 0, 5, tzinfo=timezone.utc), datetime(2026, 7, 18, tzinfo=timezone.utc)),
            ("1h", datetime(2026, 7, 19, 14, 5, tzinfo=timezone.utc), datetime(2026, 7, 19, 13, tzinfo=timezone.utc)),
            ("4h", datetime(2026, 7, 19, 14, 5, tzinfo=timezone.utc), datetime(2026, 7, 19, 8, tzinfo=timezone.utc)),
            # 1w opens Thursday (epoch-anchored). 2026-07-19 is a Sunday inside
            # the week that opened Thu 07-16, so the last CLOSED week is 07-09.
            ("1w", datetime(2026, 7, 19, 12, tzinfo=timezone.utc), datetime(2026, 7, 9, tzinfo=timezone.utc)),
            # Thursday 00:00 itself: the week that just opened is forming, so
            # the last closed one is the previous Thursday.
            ("1w", datetime(2026, 7, 16, 0, 0, tzinfo=timezone.utc), datetime(2026, 7, 9, tzinfo=timezone.utc)),
            # One second before a boundary stays in the prior week.
            ("1w", datetime(2026, 7, 15, 23, 59, 59, tzinfo=timezone.utc), datetime(2026, 7, 2, tzinfo=timezone.utc)),
        ],
    )
    def test_is_one_period_behind_the_floor(self, timeframe, now, expected):
        assert _last_closed_period(now, timeframe) == expected

    def test_the_daily_job_at_2310_utc_cannot_close_todays_bar(self):
        """The exact pre-fix failure: 01:10 CEST = 23:10 UTC, 50 min before close."""
        now = datetime(2026, 7, 18, 23, 10, tzinfo=timezone.utc)

        assert _floor_timestamp(now, "1d") == datetime(2026, 7, 18, tzinfo=timezone.utc)
        assert _last_closed_period(now, "1d") == datetime(2026, 7, 17, tzinfo=timezone.utc)

    def test_the_hourly_job_at_05_past_cannot_close_this_hour(self):
        now = datetime(2026, 7, 19, 14, 5, tzinfo=timezone.utc)

        assert _floor_timestamp(now, "1h") == datetime(2026, 7, 19, 14, tzinfo=timezone.utc)
        assert _last_closed_period(now, "1h") == datetime(2026, 7, 19, 13, tzinfo=timezone.utc)

    def test_weekly_floors_to_the_exchange_anchor_not_the_iso_week(self):
        """Weeks open THURSDAY, because KuCoin buckets by epoch modulo.

        This asserted Monday until 2026-08-09. Monday is the ISO convention and
        what Binance/TradingView use, but KuCoin is 4 days off it, so the cutoff
        landed behind the newest stored bar and `run_update` early-returned
        "up to date" forever. See test_weekly_update_is_not_stalled_by_the_anchor.
        """
        now = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)  # a Sunday

        assert _floor_timestamp(now, "1w") == datetime(2026, 7, 16, tzinfo=timezone.utc)
        assert _last_closed_period(now, "1w") == datetime(2026, 7, 9, tzinfo=timezone.utc)

    def test_every_weekly_boundary_is_epoch_aligned(self):
        """The invariant that defines the anchor: ts % 604800 == 0.

        Stronger than pinning a weekday — it is the actual rule KuCoin and
        ccxt's own `round_timeframe` implement, and it cannot drift.
        """
        week = 7 * 24 * 3600
        for day in range(0, 30):
            now = datetime(2026, 7, 1, 6, 30, tzinfo=timezone.utc) + timedelta(days=day)
            for fn in (_floor_timestamp, _last_closed_period):
                boundary = fn(now, "1w")
                assert int(boundary.timestamp()) % week == 0
                assert boundary.weekday() == 3  # Thursday

    def test_weekly_update_is_not_stalled_by_the_anchor(self):
        """Regression for the 2026-07-19..08-09 stall.

        `run_update` computes `fetch_from = last_stored + 1 period` and returns
        early when that exceeds `_last_closed_period`. With a Monday floor and a
        Thursday-anchored store, `fetch_from` was permanently the greater of the
        two, so nothing was ever fetched. Asserted against the real stored state
        on the day this was found.
        """
        last_stored = datetime(2026, 7, 23, tzinfo=timezone.utc)  # real: newest bar, a Thursday
        now = datetime(2026, 8, 9, 1, 10, tzinfo=timezone.utc)  # real: job time, a Sunday

        fetch_from = last_stored + timedelta(weeks=1)
        last_closed = _last_closed_period(now, "1w")

        assert last_closed == datetime(2026, 7, 30, tzinfo=timezone.utc)
        assert fetch_from <= last_closed, "would early-return 'up to date' and never advance"


class TestPeriodsBehind:
    """Freshness measured against the last closed period, not against `now`.

    The old watchdog compared `now - timestamp` to a fixed threshold. A bar's
    timestamp age oscillates by a full period between writes, so that comparison
    is only correct at one hour of the day.
    """

    def test_a_current_bar_is_zero_behind_at_every_hour_of_the_period(self):
        """The property the wall-clock threshold did not have.

        A daily collection written on schedule is 0 behind whether you ask at
        05:00 UTC or at 23:00 UTC. Under the old 36h threshold the same
        collection was 'fresh' at 05:00 (29h) and 'stale' at 19:00 (43h).
        """
        for hour in range(24):
            now = datetime(2026, 8, 9, hour, 30, tzinfo=timezone.utc)
            latest = _last_closed_period(now, "1d")
            assert periods_behind(latest, now, "1d") == 0, f"failed at {hour:02d}:30"

    def test_the_false_alarm_that_started_this(self):
        """2026-08-09 19:09 UTC: the daily job had run correctly at 01:10 and
        stored the 08-08 bar. Raw age was 43h against a 36h threshold, so the
        watchdog fired a RED alert for 34 collections with nothing wrong."""
        now = datetime(2026, 8, 9, 19, 9, tzinfo=timezone.utc)
        latest = datetime(2026, 8, 8, tzinfo=timezone.utc)

        assert (now - latest) > timedelta(hours=36)  # what the old check saw
        assert periods_behind(latest, now, "1d") == 0  # what was actually true

    def test_a_genuinely_missed_day_is_caught(self):
        now = datetime(2026, 8, 9, 5, 0, tzinfo=timezone.utc)

        assert periods_behind(datetime(2026, 8, 8, tzinfo=timezone.utc), now, "1d") == 0
        assert periods_behind(datetime(2026, 8, 7, tzinfo=timezone.utc), now, "1d") == 1
        assert periods_behind(datetime(2026, 8, 4, tzinfo=timezone.utc), now, "1d") == 4

    def test_the_weekly_stall_is_visible(self):
        """The state weekly sat in for three weeks while nothing alerted."""
        now = datetime(2026, 8, 9, 5, 0, tzinfo=timezone.utc)
        latest = datetime(2026, 7, 23, tzinfo=timezone.utc)  # real stored value

        assert periods_behind(latest, now, "1w") == 1

    def test_hourly_lags_one_period_by_construction(self):
        """The hourly job runs at :05, so the hour that closed at :00 is written
        five minutes later — 1 behind is normal, not a fault."""
        now = datetime(2026, 8, 9, 5, 0, tzinfo=timezone.utc)
        latest = datetime(2026, 8, 9, 3, 0, tzinfo=timezone.utc)

        assert periods_behind(latest, now, "1h") == 1

    def test_a_bar_from_the_future_is_never_negative(self):
        now = datetime(2026, 8, 9, 5, 0, tzinfo=timezone.utc)
        ahead = datetime(2026, 8, 20, tzinfo=timezone.utc)

        assert periods_behind(ahead, now, "1d") == 0


class TestDropUnclosed:
    def _frame(self, stamps):
        return pd.DataFrame({"Close": [100.0] * len(stamps)}, index=pd.DatetimeIndex(stamps))

    def test_drops_the_in_progress_daily_candle(self):
        now = datetime(2026, 7, 18, 23, 10, tzinfo=timezone.utc)
        df = self._frame([
            datetime(2026, 7, 16, tzinfo=timezone.utc),
            datetime(2026, 7, 17, tzinfo=timezone.utc),
            datetime(2026, 7, 18, tzinfo=timezone.utc),  # still open
        ])

        out = _drop_unclosed(df, "1d", now)

        assert list(out.index) == [
            pd.Timestamp("2026-07-16", tz="UTC"),
            pd.Timestamp("2026-07-17", tz="UTC"),
        ]

    def test_keeps_the_day_once_it_has_closed(self):
        now = datetime(2026, 7, 19, 0, 5, tzinfo=timezone.utc)
        df = self._frame([
            datetime(2026, 7, 17, tzinfo=timezone.utc),
            datetime(2026, 7, 18, tzinfo=timezone.utc),
        ])

        assert len(_drop_unclosed(df, "1d", now)) == 2

    def test_drops_the_forming_hour(self):
        now = datetime(2026, 7, 19, 14, 5, tzinfo=timezone.utc)
        df = self._frame([
            datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
            datetime(2026, 7, 19, 13, tzinfo=timezone.utc),
            datetime(2026, 7, 19, 14, tzinfo=timezone.utc),  # 5 minutes old
        ])

        out = _drop_unclosed(df, "1h", now)

        assert pd.Timestamp("2026-07-19 14:00", tz="UTC") not in out.index
        assert len(out) == 2

    def test_drops_the_forming_week_and_keeps_closed_ones(self):
        """Thursday-anchored: on Sun 08-09, the week that opened Thu 08-06 is
        still forming and must not be stored; 07-23 and 07-30 have closed."""
        now = datetime(2026, 8, 9, 1, 10, tzinfo=timezone.utc)
        df = self._frame([
            datetime(2026, 7, 23, tzinfo=timezone.utc),
            datetime(2026, 7, 30, tzinfo=timezone.utc),
            datetime(2026, 8, 6, tzinfo=timezone.utc),  # still open
        ])

        out = _drop_unclosed(df, "1w", now)

        assert list(out.index) == [
            pd.Timestamp("2026-07-23", tz="UTC"),
            pd.Timestamp("2026-07-30", tz="UTC"),
        ]

    def test_empty_and_none_are_passed_through(self):
        assert _drop_unclosed(None, "1d") is None
        assert _drop_unclosed(pd.DataFrame(), "1d").empty

    def test_result_can_be_empty_when_nothing_has_closed(self):
        """`run_update` must treat this as 'nothing to do', not as an error."""
        now = datetime(2026, 7, 18, 23, 10, tzinfo=timezone.utc)
        df = self._frame([datetime(2026, 7, 18, tzinfo=timezone.utc)])

        assert _drop_unclosed(df, "1d", now).empty


class TestRefreshWindow:
    """`refresh_last` re-fetches the most recent N closed candles.

    The gap check only looks at the newest stored timestamp, so a candle the
    exchange later revises can never be noticed. This is the rolling self-heal.
    """

    def _fetch_from(self, last_ts, last_closed, delta, refresh_last):
        """Mirror of the window arithmetic in `run_update`."""
        fetch_from = last_ts + delta
        if refresh_last > 0:
            fetch_from = min(fetch_from, last_closed - (refresh_last - 1) * delta)
        return fetch_from

    def test_without_refresh_it_starts_after_what_is_stored(self):
        last_ts = datetime(2026, 7, 17, tzinfo=timezone.utc)
        last_closed = datetime(2026, 7, 18, tzinfo=timezone.utc)

        got = self._fetch_from(last_ts, last_closed, timedelta(days=1), 0)

        assert got == datetime(2026, 7, 18, tzinfo=timezone.utc)

    def test_refresh_two_reaches_back_over_the_stored_day(self):
        last_ts = datetime(2026, 7, 18, tzinfo=timezone.utc)
        last_closed = datetime(2026, 7, 18, tzinfo=timezone.utc)

        got = self._fetch_from(last_ts, last_closed, timedelta(days=1), 2)

        assert got == datetime(2026, 7, 17, tzinfo=timezone.utc)

    def test_refresh_never_widens_an_already_larger_gap(self):
        """A long outage must still be filled from where the data stops."""
        last_ts = datetime(2026, 7, 1, tzinfo=timezone.utc)
        last_closed = datetime(2026, 7, 18, tzinfo=timezone.utc)

        got = self._fetch_from(last_ts, last_closed, timedelta(days=1), 2)

        assert got == datetime(2026, 7, 2, tzinfo=timezone.utc)

    def test_up_to_date_check_uses_the_closed_period(self):
        """At 23:10 UTC with yesterday stored, there is nothing to fetch."""
        last_ts = datetime(2026, 7, 17, tzinfo=timezone.utc)
        now = datetime(2026, 7, 18, 23, 10, tzinfo=timezone.utc)
        last_closed = _last_closed_period(now, "1d")

        fetch_from = self._fetch_from(last_ts, last_closed, timedelta(days=1), 0)

        assert fetch_from > last_closed  # → run_update returns early
