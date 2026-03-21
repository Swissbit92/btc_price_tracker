"""Tests for btc_tracker_mongodb.extract_perp — perpetual futures data extraction."""

import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from btc_tracker_mongodb.extract_perp import (
    _normalize_perp_symbol,
    fetch_perp_candles,
    fetch_funding_rate_history,
)


# ---------------------------------------------------------------------------
# _normalize_perp_symbol
# ---------------------------------------------------------------------------

class TestNormalizePerpSymbol:
    def test_btc(self):
        assert _normalize_perp_symbol("BTC-USDT") == "BTC/USDT:USDT"

    def test_eth(self):
        assert _normalize_perp_symbol("ETH-USDT") == "ETH/USDT:USDT"

    def test_sol(self):
        assert _normalize_perp_symbol("SOL-USDT") == "SOL/USDT:USDT"

    def test_unknown_symbol_fallback(self):
        """Symbols not in PERP_SYMBOL_MAP still get normalized via string replace."""
        result = _normalize_perp_symbol("UNKNOWN-USDT")
        assert result == "UNKNOWN/USDT:USDT"


# ---------------------------------------------------------------------------
# fetch_perp_candles
# ---------------------------------------------------------------------------

class TestFetchPerpCandles:
    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_returns_correct_dataframe_structure(self, mock_get_ex):
        mock_ex = MagicMock()
        mock_ex.fetch_ohlcv.return_value = [
            [1700000000000, 35000.0, 35500.0, 34800.0, 35200.0, 100.5],
        ]
        mock_get_ex.return_value = mock_ex

        df = fetch_perp_candles("BTC-USDT", "1h", since_ms=1700000000000, limit=1)

        assert isinstance(df, pd.DataFrame)
        assert df.index.name == "timestamp"
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert len(df) == 1

    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_correct_values(self, mock_get_ex):
        mock_ex = MagicMock()
        mock_ex.fetch_ohlcv.return_value = [
            [1700000000000, 35000.0, 35500.0, 34800.0, 35200.0, 100.5],
        ]
        mock_get_ex.return_value = mock_ex

        df = fetch_perp_candles("BTC-USDT", "1h", since_ms=1700000000000, limit=1)

        row = df.iloc[0]
        assert row["Open"] == 35000.0
        assert row["High"] == 35500.0
        assert row["Low"] == 34800.0
        assert row["Close"] == 35200.0
        assert row["Volume"] == 100.5

    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_timestamp_is_utc(self, mock_get_ex):
        mock_ex = MagicMock()
        mock_ex.fetch_ohlcv.return_value = [
            [1700000000000, 35000.0, 35500.0, 34800.0, 35200.0, 100.5],
        ]
        mock_get_ex.return_value = mock_ex

        df = fetch_perp_candles("BTC-USDT", "1h", since_ms=1700000000000, limit=1)

        ts = df.index[0]
        assert ts.tzinfo is not None
        expected = datetime.fromtimestamp(1700000000000 / 1000, tz=timezone.utc)
        assert ts == expected

    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_empty_response_returns_empty_dataframe(self, mock_get_ex):
        mock_ex = MagicMock()
        mock_ex.fetch_ohlcv.return_value = []
        mock_get_ex.return_value = mock_ex

        df = fetch_perp_candles("BTC-USDT", "1h", since_ms=1700000000000, limit=10)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert df.index.name == "timestamp"
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]

    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_multiple_candles_sorted(self, mock_get_ex):
        mock_ex = MagicMock()
        # Return candles out of order to verify sorting
        mock_ex.fetch_ohlcv.return_value = [
            [1700003600000, 35200.0, 35600.0, 35100.0, 35400.0, 80.0],
            [1700000000000, 35000.0, 35500.0, 34800.0, 35200.0, 100.5],
        ]
        mock_get_ex.return_value = mock_ex

        df = fetch_perp_candles("BTC-USDT", "1h", since_ms=1700000000000, limit=2)

        assert len(df) == 2
        assert df.index[0] < df.index[1]

    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_deduplication_keeps_last(self, mock_get_ex):
        mock_ex = MagicMock()
        # Two candles with same timestamp — last should win
        mock_ex.fetch_ohlcv.return_value = [
            [1700000000000, 35000.0, 35500.0, 34800.0, 35200.0, 100.5],
            [1700000000000, 36000.0, 36500.0, 35800.0, 36200.0, 200.0],
        ]
        mock_get_ex.return_value = mock_ex

        df = fetch_perp_candles("BTC-USDT", "1h", since_ms=1700000000000, limit=2)

        assert len(df) == 1
        assert df.iloc[0]["Close"] == 36200.0  # last occurrence wins

    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_pagination(self, mock_get_ex):
        """When limit > 500, it should paginate (batch_size=500)."""
        mock_ex = MagicMock()
        # First call returns 500 candles, second call returns 100 more
        batch1 = [[1700000000000 + i * 3_600_000, 35000, 35500, 34800, 35200, 100]
                   for i in range(500)]
        batch2 = [[1700000000000 + (500 + i) * 3_600_000, 35000, 35500, 34800, 35200, 100]
                   for i in range(100)]
        mock_ex.fetch_ohlcv.side_effect = [batch1, batch2]
        mock_get_ex.return_value = mock_ex

        df = fetch_perp_candles("BTC-USDT", "1h", since_ms=1700000000000, limit=600)

        assert len(df) == 600
        assert mock_ex.fetch_ohlcv.call_count == 2


# ---------------------------------------------------------------------------
# fetch_funding_rate_history
# ---------------------------------------------------------------------------

def _make_ccxt_funding_record(ts_ms, rate=0.0001, mark=35200.5, index=35190.0):
    """Helper to create a CCXT funding rate record."""
    return {
        "timestamp": ts_ms,
        "datetime": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(),
        "symbol": "BTC/USDT:USDT",
        "fundingRate": rate,
        "markPrice": mark,
        "indexPrice": index,
    }


class TestFetchFundingRateHistory:
    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_returns_correct_columns(self, mock_get_ex):
        mock_ex = MagicMock()
        mock_ex.fetch_funding_rate_history.return_value = [
            _make_ccxt_funding_record(1700000000000),
            _make_ccxt_funding_record(1700028800000),  # +8h
        ]
        mock_get_ex.return_value = mock_ex

        df = fetch_funding_rate_history("BTC-USDT", since_ms=1700000000000, limit=2)

        assert df.index.name == "timestamp"
        expected_cols = ["period_start", "funding_rate", "mark_price",
                         "index_price", "basis_pct", "interval_hours"]
        assert list(df.columns) == expected_cols

    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_period_start_computed(self, mock_get_ex):
        """period_start should be settlement time minus interval_hours."""
        mock_ex = MagicMock()
        ts1 = 1700000000000
        ts2 = ts1 + 8 * 3_600_000  # +8h
        mock_ex.fetch_funding_rate_history.return_value = [
            _make_ccxt_funding_record(ts1),
            _make_ccxt_funding_record(ts2),
        ]
        mock_get_ex.return_value = mock_ex

        df = fetch_funding_rate_history("BTC-USDT", since_ms=ts1, limit=2)

        # Both records have 8h interval
        assert df["interval_hours"].iloc[0] == 8.0
        assert df["interval_hours"].iloc[1] == 8.0
        # period_start = settlement - 8h
        expected_start_0 = datetime.fromtimestamp(ts1 / 1000, tz=timezone.utc) - timedelta(hours=8)
        expected_start_1 = datetime.fromtimestamp(ts2 / 1000, tz=timezone.utc) - timedelta(hours=8)
        assert df["period_start"].iloc[0] == expected_start_0
        assert df["period_start"].iloc[1] == expected_start_1

    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_basis_pct_computed(self, mock_get_ex):
        """basis_pct = (mark - index) / index * 100."""
        mock_ex = MagicMock()
        mark, index = 35200.0, 35000.0
        mock_ex.fetch_funding_rate_history.return_value = [
            _make_ccxt_funding_record(1700000000000, mark=mark, index=index),
            _make_ccxt_funding_record(1700028800000, mark=mark, index=index),
        ]
        mock_get_ex.return_value = mock_ex

        df = fetch_funding_rate_history("BTC-USDT", since_ms=1700000000000, limit=2)

        expected_basis = (mark - index) / index * 100
        assert abs(df["basis_pct"].iloc[0] - expected_basis) < 1e-10

    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_none_mark_index_graceful(self, mock_get_ex):
        """When markPrice or indexPrice is None, basis_pct should be None."""
        mock_ex = MagicMock()
        rec = _make_ccxt_funding_record(1700000000000)
        rec["markPrice"] = None
        rec["indexPrice"] = None
        # Need two records so interval_hours can be computed
        rec2 = _make_ccxt_funding_record(1700028800000)
        rec2["markPrice"] = None
        rec2["indexPrice"] = None
        mock_ex.fetch_funding_rate_history.return_value = [rec, rec2]
        mock_get_ex.return_value = mock_ex

        df = fetch_funding_rate_history("BTC-USDT", since_ms=1700000000000, limit=2)

        assert pd.isna(df["mark_price"].iloc[0])
        assert pd.isna(df["index_price"].iloc[0])
        assert pd.isna(df["basis_pct"].iloc[0])

    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_interval_hours_from_consecutive(self, mock_get_ex):
        """interval_hours derived from gap between consecutive records."""
        mock_ex = MagicMock()
        ts1 = 1700000000000
        ts2 = ts1 + 8 * 3_600_000   # 8h later
        ts3 = ts2 + 8 * 3_600_000   # 8h later
        mock_ex.fetch_funding_rate_history.return_value = [
            _make_ccxt_funding_record(ts1),
            _make_ccxt_funding_record(ts2),
            _make_ccxt_funding_record(ts3),
        ]
        mock_get_ex.return_value = mock_ex

        df = fetch_funding_rate_history("BTC-USDT", since_ms=ts1, limit=3)

        assert df["interval_hours"].iloc[0] == 8.0  # first looks ahead
        assert df["interval_hours"].iloc[1] == 8.0  # gap from ts1 to ts2
        assert df["interval_hours"].iloc[2] == 8.0  # gap from ts2 to ts3

    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_single_record_interval_hours_none(self, mock_get_ex):
        """Single record => interval_hours is None (no neighbors to compare)."""
        mock_ex = MagicMock()
        mock_ex.fetch_funding_rate_history.return_value = [
            _make_ccxt_funding_record(1700000000000),
        ]
        mock_get_ex.return_value = mock_ex

        df = fetch_funding_rate_history("BTC-USDT", since_ms=1700000000000, limit=1)

        assert pd.isna(df["interval_hours"].iloc[0])

    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_empty_returns_empty_dataframe(self, mock_get_ex):
        mock_ex = MagicMock()
        mock_ex.fetch_funding_rate_history.return_value = []
        mock_get_ex.return_value = mock_ex

        df = fetch_funding_rate_history("BTC-USDT", since_ms=1700000000000, limit=10)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert df.index.name == "timestamp"
        expected_cols = ["period_start", "funding_rate", "mark_price",
                         "index_price", "basis_pct", "interval_hours"]
        assert list(df.columns) == expected_cols

    @patch("btc_tracker_mongodb.extract_perp._get_futures_exchange")
    def test_single_record_period_start_none(self, mock_get_ex):
        """Single record => interval unknown => period_start is None."""
        mock_ex = MagicMock()
        mock_ex.fetch_funding_rate_history.return_value = [
            _make_ccxt_funding_record(1700000000000),
        ]
        mock_get_ex.return_value = mock_ex

        df = fetch_funding_rate_history("BTC-USDT", since_ms=1700000000000, limit=1)

        assert pd.isna(df["period_start"].iloc[0])
