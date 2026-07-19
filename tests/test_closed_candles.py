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

    def test_weekly_floors_to_the_previous_monday(self):
        now = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)  # a Sunday

        assert _last_closed_period(now, "1w") == datetime(2026, 7, 6, tzinfo=timezone.utc)


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
