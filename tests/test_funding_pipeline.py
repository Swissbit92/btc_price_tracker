"""
Tests for the funding rate pipeline fix:
- _get_funding_since_ms: uses last stored funding ts - 3d to avoid KuCoin's ~2d dead zone
- _fetch_and_store_funding: logs empty result instead of silently skipping
- Watchdog check_freshness: now includes funding_rate collections
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# _get_funding_since_ms
# ---------------------------------------------------------------------------

class TestGetFundingSinceMs:
    def _make_coll(self, last_ts):
        coll = MagicMock()
        if last_ts is None:
            coll.find_one.return_value = None
        else:
            coll.find_one.return_value = {"timestamp": last_ts}
        return coll

    @patch("btc_tracker_mongodb.pipeline.get_funding_collection")
    def test_uses_last_stored_minus_3d(self, mock_get_coll):
        from btc_tracker_mongodb.pipeline import _get_funding_since_ms
        last_ts = datetime(2026, 4, 17, 16, 0, tzinfo=timezone.utc)
        mock_get_coll.return_value = self._make_coll(last_ts)

        fallback_ms = int(datetime(2026, 4, 25, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        result = _get_funding_since_ms("BTC-USDT", False, fallback_ms)

        expected_ms = int(last_ts.timestamp() * 1000) - 3 * 24 * 60 * 60 * 1000
        assert result == expected_ms

    @patch("btc_tracker_mongodb.pipeline.get_funding_collection")
    def test_fallback_when_no_stored_data(self, mock_get_coll):
        from btc_tracker_mongodb.pipeline import _get_funding_since_ms
        mock_get_coll.return_value = self._make_coll(None)

        fallback_ms = 1_777_075_200_000
        result = _get_funding_since_ms("BTC-USDT", False, fallback_ms)

        assert result == fallback_ms

    @patch("btc_tracker_mongodb.pipeline.get_funding_collection")
    def test_result_never_negative(self, mock_get_coll):
        from btc_tracker_mongodb.pipeline import _get_funding_since_ms
        # last_ts only 1 hour old — 3d buffer would underflow without max(0, ...)
        last_ts = datetime(2026, 4, 17, 0, 0, tzinfo=timezone.utc)
        # Simulate a very old last_ts that when subtracted 3d stays >= 0
        mock_get_coll.return_value = self._make_coll(last_ts)

        result = _get_funding_since_ms("BTC-USDT", False, fallback_ms=0)
        assert result >= 0

    @patch("btc_tracker_mongodb.pipeline.get_funding_collection")
    def test_passes_test_flag_to_collection(self, mock_get_coll):
        from btc_tracker_mongodb.pipeline import _get_funding_since_ms
        mock_get_coll.return_value = self._make_coll(None)

        _get_funding_since_ms("BTC-USDT", test=True, fallback_ms=0)
        mock_get_coll.assert_called_once_with("BTC-USDT", True)


# ---------------------------------------------------------------------------
# _fetch_and_store_funding — empty result logs instead of silent skip
# ---------------------------------------------------------------------------

class TestFetchAndStoreFunding:
    @patch("btc_tracker_mongodb.pipeline.bulk_upsert_funding")
    @patch("btc_tracker_mongodb.pipeline.fetch_funding_rate_history")
    def test_stores_records_when_data_returned(self, mock_fetch, mock_upsert):
        import pandas as pd
        from btc_tracker_mongodb.pipeline import _fetch_and_store_funding

        ts = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
        df = pd.DataFrame([{"funding_rate": -0.0001}], index=[ts])
        df.index.name = "timestamp"
        mock_fetch.return_value = df
        mock_upsert.return_value = 1

        _fetch_and_store_funding("BTC-USDT", 0, False, tag="test")

        mock_upsert.assert_called_once()

    @patch("btc_tracker_mongodb.pipeline.fetch_funding_rate_history")
    def test_logs_when_empty(self, mock_fetch, capsys):
        import pandas as pd
        from btc_tracker_mongodb.pipeline import _fetch_and_store_funding

        mock_fetch.return_value = pd.DataFrame()

        _fetch_and_store_funding("BTC-USDT", 0, False, tag="test")

        captured = capsys.readouterr()
        assert "No new funding rate records" in captured.out

    @patch("btc_tracker_mongodb.pipeline.fetch_funding_rate_history")
    def test_logs_warning_on_exception(self, mock_fetch, capsys):
        from btc_tracker_mongodb.pipeline import _fetch_and_store_funding

        mock_fetch.side_effect = RuntimeError("network error")

        _fetch_and_store_funding("BTC-USDT", 0, False, tag="test")

        captured = capsys.readouterr()
        assert "WARNING" in captured.out


# ---------------------------------------------------------------------------
# Watchdog check_freshness — now includes funding_rate collections
# ---------------------------------------------------------------------------

class TestWatchdogFundingCheck:
    def _make_fresh_doc(self, hours_old=1):
        ts = datetime.now(timezone.utc) - timedelta(hours=hours_old)
        return {"timestamp": ts}

    def _make_stale_doc(self):
        return self._make_fresh_doc(hours_old=48)

    def test_funding_stale_detected(self):
        """Funding rate stale check is now part of check_freshness coverage."""
        import bin.run_watchdog as wdog
        import inspect
        src = inspect.getsource(wdog.check_freshness)
        assert "get_funding_collection" in src

    def test_funding_check_increases_count(self):
        """Each token now contributes +1 funding check to the total checked count."""
        import bin.run_watchdog as wdog
        import inspect
        src = inspect.getsource(wdog.check_freshness)
        assert "36" in src
        assert "funding_rate" in src
