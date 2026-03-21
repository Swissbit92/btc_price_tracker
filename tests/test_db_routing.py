"""Tests for db.py collection routing — verify correct collection names without MongoDB."""

import pytest
from unittest.mock import patch, MagicMock

from btc_tracker_mongodb.db import get_collection, get_funding_collection


# ---------------------------------------------------------------------------
# get_collection routing
# ---------------------------------------------------------------------------

class TestGetCollectionRouting:
    @patch("btc_tracker_mongodb.db.get_db")
    def test_perp_1h(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        get_collection("BTC-USDT", "1h", False, "perp")

        mock_db.__getitem__.assert_called_once_with("btc_perp_1h_price_data")

    @patch("btc_tracker_mongodb.db.get_db")
    def test_spot_1h_explicit(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        get_collection("BTC-USDT", "1h", False, "spot")

        mock_db.__getitem__.assert_called_once_with("btc_1h_price_data")

    @patch("btc_tracker_mongodb.db.get_db")
    def test_default_is_spot(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        get_collection("BTC-USDT", "1h", False)

        mock_db.__getitem__.assert_called_once_with("btc_1h_price_data")

    @patch("btc_tracker_mongodb.db.get_db")
    def test_perp_4h(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        get_collection("ETH-USDT", "4h", False, "perp")

        mock_db.__getitem__.assert_called_once_with("eth_perp_4h_price_data")

    @patch("btc_tracker_mongodb.db.get_db")
    def test_perp_daily(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        get_collection("SOL-USDT", "1d", False, "perp")

        mock_db.__getitem__.assert_called_once_with("sol_perp_daily_price_data")

    @patch("btc_tracker_mongodb.db.get_db")
    def test_spot_daily(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        get_collection("SOL-USDT", "1d", False, "spot")

        mock_db.__getitem__.assert_called_once_with("sol_daily_price_data")

    @patch("btc_tracker_mongodb.db.get_db")
    def test_test_flag_passed_through(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        get_collection("BTC-USDT", "1h", True, "perp")

        mock_get_db.assert_called_once_with(True)

    @patch("btc_tracker_mongodb.db.get_db")
    def test_prod_flag_passed_through(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        get_collection("BTC-USDT", "1h", False, "spot")

        mock_get_db.assert_called_once_with(False)


# ---------------------------------------------------------------------------
# get_funding_collection routing
# ---------------------------------------------------------------------------

class TestGetFundingCollectionRouting:
    @patch("btc_tracker_mongodb.db.get_db")
    def test_btc_funding(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        get_funding_collection("BTC-USDT")

        mock_db.__getitem__.assert_called_once_with("btc_funding_rate_data")

    @patch("btc_tracker_mongodb.db.get_db")
    def test_eth_funding(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        get_funding_collection("ETH-USDT")

        mock_db.__getitem__.assert_called_once_with("eth_funding_rate_data")

    @patch("btc_tracker_mongodb.db.get_db")
    def test_sol_funding(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        get_funding_collection("SOL-USDT")

        mock_db.__getitem__.assert_called_once_with("sol_funding_rate_data")

    @patch("btc_tracker_mongodb.db.get_db")
    def test_test_db_flag(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        get_funding_collection("BTC-USDT", test=True)

        mock_get_db.assert_called_once_with(True)

    @patch("btc_tracker_mongodb.db.get_db")
    def test_prod_db_flag(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        get_funding_collection("BTC-USDT", test=False)

        mock_get_db.assert_called_once_with(False)
