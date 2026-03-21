"""Tests for _align_funding_to_candles from btc_tracker_mongodb.pipeline."""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

from btc_tracker_mongodb.pipeline import _align_funding_to_candles


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_funding_df(timestamps, rates, mark_prices=None, index_prices=None, interval_hours=8):
    """Helper to create funding rate DataFrames for testing.

    Args:
        timestamps: list of UTC datetime objects (settlement times)
        rates: list of float funding rates
        mark_prices: list of float or None (defaults to 35000.0 for each)
        index_prices: list of float or None (defaults to 34990.0 for each)
        interval_hours: hours per funding period (used to compute period_start)
    """
    n = len(timestamps)
    if mark_prices is None:
        mark_prices = [35000.0] * n
    if index_prices is None:
        index_prices = [34990.0] * n

    period_starts = [ts - timedelta(hours=interval_hours) for ts in timestamps]
    basis_pcts = []
    for m, i in zip(mark_prices, index_prices):
        if m is not None and i is not None and i != 0:
            basis_pcts.append((m - i) / i * 100)
        else:
            basis_pcts.append(None)

    df = pd.DataFrame({
        "timestamp": timestamps,
        "period_start": period_starts,
        "funding_rate": rates,
        "mark_price": mark_prices,
        "index_price": index_prices,
        "basis_pct": basis_pcts,
        "interval_hours": [float(interval_hours)] * n,
    })
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)
    return df


def _make_ohlcv_df(timestamps):
    """Helper to create simple OHLCV DataFrames for testing.

    Generates synthetic price data for the given timestamps.
    """
    n = len(timestamps)
    df = pd.DataFrame({
        "timestamp": timestamps,
        "Open": [35000.0 + i for i in range(n)],
        "High": [35100.0 + i for i in range(n)],
        "Low": [34900.0 + i for i in range(n)],
        "Close": [35050.0 + i for i in range(n)],
        "Volume": [100.0 + i for i in range(n)],
    })
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)
    return df


# ---------------------------------------------------------------------------
# Daily alignment
# ---------------------------------------------------------------------------

class TestAlignDaily:
    def test_three_funding_records_per_day_summed(self):
        """Daily candles should get the SUM of all funding rates in that UTC day.

        Grouping uses period_start date (settlement minus interval), so we
        place 3 settlements whose period_start all fall on Jan 15:
            settlement 08:00 -> period_start 00:00 (Jan 15)
            settlement 16:00 -> period_start 08:00 (Jan 15)
            settlement 00:00+1d -> period_start 16:00 (Jan 15)
        """
        base = datetime(2024, 1, 15, tzinfo=timezone.utc)

        # 3 funding settlements whose period_start falls on Jan 15
        funding_ts = [
            base + timedelta(hours=8),   # period_start = Jan 15 00:00
            base + timedelta(hours=16),  # period_start = Jan 15 08:00
            base + timedelta(hours=24),  # period_start = Jan 15 16:00
        ]
        rates = [0.0001, 0.0002, 0.0003]
        funding_df = _make_funding_df(funding_ts, rates)

        # One daily candle on Jan 15
        ohlcv_df = _make_ohlcv_df([base])

        result = _align_funding_to_candles(funding_df, ohlcv_df, "1d")

        assert "Funding_Rate" in result.columns
        assert "Mark_Price" in result.columns
        assert "Basis_Pct" in result.columns
        # Sum of rates for that day (grouped by period_start date = Jan 15)
        expected_sum = 0.0001 + 0.0002 + 0.0003
        assert abs(result["Funding_Rate"].iloc[0] - expected_sum) < 1e-10

    def test_multiple_days(self):
        """Two daily candles each get their own day's summed funding rate.

        period_start = settlement - 8h, grouping by period_start date:
            settlement 08:00 Jan15 -> period_start 00:00 Jan15 (day1)
            settlement 16:00 Jan15 -> period_start 08:00 Jan15 (day1)
            settlement 00:00 Jan16 -> period_start 16:00 Jan15 (day1)
            settlement 08:00 Jan16 -> period_start 00:00 Jan16 (day2)
            settlement 16:00 Jan16 -> period_start 08:00 Jan16 (day2)
            settlement 00:00 Jan17 -> period_start 16:00 Jan16 (day2)
        """
        day1 = datetime(2024, 1, 15, tzinfo=timezone.utc)
        day2 = datetime(2024, 1, 16, tzinfo=timezone.utc)

        funding_ts = [
            day1 + timedelta(hours=8),   # period_start = Jan15 00:00
            day1 + timedelta(hours=16),  # period_start = Jan15 08:00
            day2,                         # period_start = Jan15 16:00
            day2 + timedelta(hours=8),   # period_start = Jan16 00:00
            day2 + timedelta(hours=16),  # period_start = Jan16 08:00
            day2 + timedelta(hours=24),  # period_start = Jan16 16:00
        ]
        rates = [0.0001, 0.0002, 0.0003, 0.0004, 0.0005, 0.0006]
        funding_df = _make_funding_df(funding_ts, rates)

        ohlcv_df = _make_ohlcv_df([day1, day2])

        result = _align_funding_to_candles(funding_df, ohlcv_df, "1d")

        assert len(result) == 2
        # day1 (Jan15): sum of rates with period_start on Jan15 = 0.0001+0.0002+0.0003
        assert abs(result["Funding_Rate"].iloc[0] - 0.0006) < 1e-10
        # day2 (Jan16): sum of rates with period_start on Jan16 = 0.0004+0.0005+0.0006
        assert abs(result["Funding_Rate"].iloc[1] - 0.0015) < 1e-10

    def test_daily_mark_price_uses_last(self):
        """Daily alignment takes the last mark_price of the day.

        All period_start dates fall on Jan 15 so they group together.
        """
        base = datetime(2024, 1, 15, tzinfo=timezone.utc)

        funding_ts = [
            base + timedelta(hours=8),   # period_start = Jan15 00:00
            base + timedelta(hours=16),  # period_start = Jan15 08:00
            base + timedelta(hours=24),  # period_start = Jan15 16:00
        ]
        rates = [0.0001, 0.0001, 0.0001]
        marks = [34000.0, 35000.0, 36000.0]
        funding_df = _make_funding_df(funding_ts, rates, mark_prices=marks)

        ohlcv_df = _make_ohlcv_df([base])

        result = _align_funding_to_candles(funding_df, ohlcv_df, "1d")

        assert result["Mark_Price"].iloc[0] == 36000.0  # last of day


# ---------------------------------------------------------------------------
# 4H alignment (merge_asof backward)
# ---------------------------------------------------------------------------

class TestAlign4H:
    def test_merge_asof_backward(self):
        """4H candles get the funding rate whose period_start <= candle time."""
        base = datetime(2024, 1, 15, tzinfo=timezone.utc)

        # Funding settlements every 8h: 08:00, 16:00, 00:00+1d
        # period_start is 8h before settlement: 00:00, 08:00, 16:00
        funding_ts = [
            base + timedelta(hours=8),
            base + timedelta(hours=16),
            base + timedelta(hours=24),
        ]
        rates = [0.0001, 0.0002, 0.0003]
        funding_df = _make_funding_df(funding_ts, rates, interval_hours=8)

        # 4H candles: 00:00, 04:00, 08:00, 12:00, 16:00, 20:00
        ohlcv_ts = [base + timedelta(hours=h) for h in range(0, 24, 4)]
        ohlcv_df = _make_ohlcv_df(ohlcv_ts)

        result = _align_funding_to_candles(funding_df, ohlcv_df, "4h")

        assert len(result) == 6
        # period_starts are: 00:00, 08:00, 16:00
        # Candle 00:00 => period_start 00:00 matches => rate 0.0001
        # Candle 04:00 => period_start 00:00 (backward) => rate 0.0001
        # Candle 08:00 => period_start 08:00 matches => rate 0.0002
        # Candle 12:00 => period_start 08:00 (backward) => rate 0.0002
        # Candle 16:00 => period_start 16:00 matches => rate 0.0003
        # Candle 20:00 => period_start 16:00 (backward) => rate 0.0003
        assert result["Funding_Rate"].iloc[0] == pytest.approx(0.0001)
        assert result["Funding_Rate"].iloc[1] == pytest.approx(0.0001)
        assert result["Funding_Rate"].iloc[2] == pytest.approx(0.0002)
        assert result["Funding_Rate"].iloc[3] == pytest.approx(0.0002)
        assert result["Funding_Rate"].iloc[4] == pytest.approx(0.0003)
        assert result["Funding_Rate"].iloc[5] == pytest.approx(0.0003)


# ---------------------------------------------------------------------------
# 1H alignment
# ---------------------------------------------------------------------------

class TestAlign1H:
    def test_1h_most_bars_filled_via_merge_asof(self):
        """1H alignment uses merge_asof backward, so bars fill from prior settlement."""
        base = datetime(2024, 1, 15, tzinfo=timezone.utc)

        # One funding settlement at 08:00 UTC (period_start = 00:00)
        funding_ts = [base + timedelta(hours=8)]
        rates = [0.0001]
        funding_df = _make_funding_df(funding_ts, rates, interval_hours=8)

        # 1H candles from 00:00 to 09:00
        ohlcv_ts = [base + timedelta(hours=h) for h in range(10)]
        ohlcv_df = _make_ohlcv_df(ohlcv_ts)

        result = _align_funding_to_candles(funding_df, ohlcv_df, "1h")

        assert len(result) == 10
        # period_start = 00:00 => candle 00:00 onward gets 0.0001 via backward merge
        # All candles at or after 00:00 should see the rate
        for i in range(10):
            assert result["Funding_Rate"].iloc[i] == pytest.approx(0.0001)


# ---------------------------------------------------------------------------
# Empty funding
# ---------------------------------------------------------------------------

class TestAlignEmpty:
    def test_empty_funding_returns_na_filled(self):
        """Empty funding DataFrame returns NaN-filled result matching OHLCV index."""
        base = datetime(2024, 1, 15, tzinfo=timezone.utc)
        ohlcv_ts = [base + timedelta(hours=h) for h in range(5)]
        ohlcv_df = _make_ohlcv_df(ohlcv_ts)

        empty_funding = pd.DataFrame(columns=[
            "period_start", "funding_rate", "mark_price",
            "index_price", "basis_pct", "interval_hours",
        ])
        empty_funding.index.name = "timestamp"

        result = _align_funding_to_candles(empty_funding, ohlcv_df, "1h")

        assert len(result) == 5
        assert "Funding_Rate" in result.columns
        assert "Mark_Price" in result.columns
        assert "Basis_Pct" in result.columns
        # All values should be NA
        assert result["Funding_Rate"].isna().all()
        assert result["Mark_Price"].isna().all()
        assert result["Basis_Pct"].isna().all()

    def test_empty_funding_daily(self):
        """Empty funding also works for daily timeframe."""
        base = datetime(2024, 1, 15, tzinfo=timezone.utc)
        ohlcv_df = _make_ohlcv_df([base, base + timedelta(days=1)])

        empty_funding = pd.DataFrame(columns=[
            "period_start", "funding_rate", "mark_price",
            "index_price", "basis_pct", "interval_hours",
        ])
        empty_funding.index.name = "timestamp"

        result = _align_funding_to_candles(empty_funding, ohlcv_df, "1d")

        assert len(result) == 2
        assert result["Funding_Rate"].isna().all()


# ---------------------------------------------------------------------------
# Variable intervals (mix of 8h and 4h)
# ---------------------------------------------------------------------------

class TestAlignVariableIntervals:
    def test_mixed_8h_and_4h_funding_intervals(self):
        """Handle a scenario where funding intervals change mid-stream."""
        base = datetime(2024, 1, 15, tzinfo=timezone.utc)

        # First two settlements: 8h apart (period_start 8h before each)
        # Last two settlements: 4h apart (period_start 4h before each)
        ts1 = base + timedelta(hours=8)   # period_start = 00:00
        ts2 = base + timedelta(hours=16)  # period_start = 08:00
        ts3 = base + timedelta(hours=20)  # period_start = 16:00 (switched to 4h interval)
        ts4 = base + timedelta(hours=24)  # period_start = 20:00

        # Build with 8h intervals for the first two, 4h for the last two
        funding_df_8h = _make_funding_df([ts1, ts2], [0.0001, 0.0002], interval_hours=8)
        funding_df_4h = _make_funding_df([ts3, ts4], [0.0003, 0.0004], interval_hours=4)
        funding_df = pd.concat([funding_df_8h, funding_df_4h])
        funding_df.sort_index(inplace=True)

        # 4H candles: 00:00, 04:00, 08:00, 12:00, 16:00, 20:00
        ohlcv_ts = [base + timedelta(hours=h) for h in range(0, 24, 4)]
        ohlcv_df = _make_ohlcv_df(ohlcv_ts)

        result = _align_funding_to_candles(funding_df, ohlcv_df, "4h")

        assert len(result) == 6
        # period_starts: 00:00, 08:00, 16:00, 20:00
        # Candle 00:00 => period_start 00:00 => rate 0.0001
        # Candle 04:00 => backward from 00:00 => rate 0.0001
        # Candle 08:00 => period_start 08:00 => rate 0.0002
        # Candle 12:00 => backward from 08:00 => rate 0.0002
        # Candle 16:00 => period_start 16:00 => rate 0.0003
        # Candle 20:00 => period_start 20:00 => rate 0.0004
        assert result["Funding_Rate"].iloc[0] == pytest.approx(0.0001)
        assert result["Funding_Rate"].iloc[2] == pytest.approx(0.0002)
        assert result["Funding_Rate"].iloc[4] == pytest.approx(0.0003)
        assert result["Funding_Rate"].iloc[5] == pytest.approx(0.0004)

    def test_daily_with_variable_intervals(self):
        """Daily alignment sums all rates regardless of interval spacing."""
        base = datetime(2024, 1, 15, tzinfo=timezone.utc)

        # 4 settlements in one day at varying intervals
        ts1 = base + timedelta(hours=4)
        ts2 = base + timedelta(hours=8)
        ts3 = base + timedelta(hours=16)
        ts4 = base + timedelta(hours=20)

        funding_df_4h = _make_funding_df([ts1, ts2], [0.0001, 0.0002], interval_hours=4)
        funding_df_8h = _make_funding_df([ts3, ts4], [0.0003, 0.0004], interval_hours=8)
        funding_df = pd.concat([funding_df_4h, funding_df_8h])
        funding_df.sort_index(inplace=True)

        ohlcv_df = _make_ohlcv_df([base])

        result = _align_funding_to_candles(funding_df, ohlcv_df, "1d")

        expected_sum = 0.0001 + 0.0002 + 0.0003 + 0.0004
        assert abs(result["Funding_Rate"].iloc[0] - expected_sum) < 1e-10


# ---------------------------------------------------------------------------
# Fallback: period_start absent or all-NaN
# ---------------------------------------------------------------------------

class TestAlignPeriodStartFallback:
    def test_daily_fallback_when_period_start_all_nan(self):
        """When period_start is all NaN, daily alignment falls back to settlement timestamp."""
        base = datetime(2024, 1, 15, tzinfo=timezone.utc)

        # 3 settlements with NaN period_start (simulates single-record batches)
        ts1 = base + timedelta(hours=0)
        ts2 = base + timedelta(hours=8)
        ts3 = base + timedelta(hours=16)

        funding_df = pd.DataFrame({
            "period_start": [pd.NaT, pd.NaT, pd.NaT],
            "funding_rate": [0.0001, 0.0002, 0.0003],
            "mark_price": [35000.0, 35100.0, 35200.0],
            "index_price": [34950.0, 35050.0, 35150.0],
            "basis_pct": [0.14, 0.14, 0.14],
            "interval_hours": [None, None, None],
        }, index=pd.DatetimeIndex([ts1, ts2, ts3], name="timestamp"))

        ohlcv_df = _make_ohlcv_df([base])

        result = _align_funding_to_candles(funding_df, ohlcv_df, "1d")

        # Should still sum rates using settlement timestamp dates as fallback
        assert len(result) == 1
        assert result["Funding_Rate"].iloc[0] == pytest.approx(0.0006)

    def test_4h_fallback_when_period_start_absent(self):
        """When period_start column is absent, 4H uses settlement timestamp."""
        base = datetime(2024, 1, 15, tzinfo=timezone.utc)

        ts1 = base + timedelta(hours=8)
        ts2 = base + timedelta(hours=16)

        # DataFrame without period_start column at all
        funding_df = pd.DataFrame({
            "funding_rate": [0.0001, 0.0002],
            "mark_price": [35000.0, 35100.0],
            "index_price": [34950.0, 35050.0],
            "basis_pct": [0.14, 0.14],
            "interval_hours": [8.0, 8.0],
        }, index=pd.DatetimeIndex([ts1, ts2], name="timestamp"))

        ohlcv_ts = [base + timedelta(hours=h) for h in range(0, 24, 4)]
        ohlcv_df = _make_ohlcv_df(ohlcv_ts)

        result = _align_funding_to_candles(funding_df, ohlcv_df, "4h")

        # Should work using settlement timestamps directly
        assert len(result) == 6
        # Candle at 08:00 should get rate 0.0001 via backward merge on settlement ts
        assert result["Funding_Rate"].iloc[2] == pytest.approx(0.0001)
