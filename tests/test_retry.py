"""Tests for btc_tracker_mongodb.retry — shared KuCoin 429000 retry/backoff helper."""

from unittest.mock import MagicMock, patch

import pytest
from ccxt.base.errors import ExchangeError

from btc_tracker_mongodb.retry import call_with_kucoin_retry


class TestCallWithKucoinRetry:
    def test_returns_result_on_first_success(self):
        fn = MagicMock(return_value="ok")

        result = call_with_kucoin_retry(fn, "a", b=1)

        assert result == "ok"
        fn.assert_called_once_with("a", b=1)

    @patch("btc_tracker_mongodb.retry.time.sleep")
    def test_retries_on_429_then_succeeds(self, mock_sleep):
        fn = MagicMock(side_effect=[ExchangeError("429000 Too Many Requests"), "ok"])

        result = call_with_kucoin_retry(fn, tries=3)

        assert result == "ok"
        assert fn.call_count == 2
        mock_sleep.assert_called_once_with(1)  # 2**0

    @patch("btc_tracker_mongodb.retry.time.sleep")
    def test_backoff_is_exponential(self, mock_sleep):
        fn = MagicMock(
            side_effect=[
                ExchangeError("429000"),
                ExchangeError("429000"),
                "ok",
            ]
        )

        result = call_with_kucoin_retry(fn, tries=3)

        assert result == "ok"
        assert mock_sleep.call_args_list == [((1,),), ((2,),)]

    @patch("btc_tracker_mongodb.retry.time.sleep")
    def test_reraises_after_exhausting_tries(self, mock_sleep):
        fn = MagicMock(side_effect=ExchangeError("429000 Too Many Requests"))

        with pytest.raises(ExchangeError):
            call_with_kucoin_retry(fn, tries=3)

        assert fn.call_count == 3
        assert mock_sleep.call_count == 2  # no sleep after the final failed attempt

    def test_non_429_exchange_error_raises_immediately(self):
        fn = MagicMock(side_effect=ExchangeError("500000 Internal Error"))

        with pytest.raises(ExchangeError):
            call_with_kucoin_retry(fn, tries=3)

        fn.assert_called_once()

    def test_non_exchange_error_propagates_immediately(self):
        fn = MagicMock(side_effect=ValueError("not an exchange error"))

        with pytest.raises(ValueError):
            call_with_kucoin_retry(fn, tries=3)

        fn.assert_called_once()
