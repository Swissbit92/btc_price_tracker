"""Tests for btc_tracker_mongodb.config — collection naming, symbol maps, constants."""


from btc_tracker_mongodb.config import (
    MARKET_TYPES,
    PERP_SYMBOL_MAP,
    TOKENS,
    get_collection_name,
    get_funding_collection_name,
)

# ---------------------------------------------------------------------------
# get_collection_name — spot (default)
# ---------------------------------------------------------------------------

class TestGetCollectionNameSpot:
    def test_btc_1h_spot(self):
        assert get_collection_name("BTC-USDT", "1h", "spot") == "btc_1h_price_data"

    def test_btc_1h_default_is_spot(self):
        assert get_collection_name("BTC-USDT", "1h") == "btc_1h_price_data"

    def test_eth_4h_spot(self):
        assert get_collection_name("ETH-USDT", "4h", "spot") == "eth_4h_price_data"

    def test_sol_daily_spot(self):
        assert get_collection_name("SOL-USDT", "1d", "spot") == "sol_daily_price_data"


# ---------------------------------------------------------------------------
# get_collection_name — perp
# ---------------------------------------------------------------------------

class TestGetCollectionNamePerp:
    def test_btc_1h_perp(self):
        assert get_collection_name("BTC-USDT", "1h", "perp") == "btc_perp_1h_price_data"

    def test_eth_4h_perp(self):
        assert get_collection_name("ETH-USDT", "4h", "perp") == "eth_perp_4h_price_data"

    def test_sol_daily_perp(self):
        assert get_collection_name("SOL-USDT", "1d", "perp") == "sol_perp_daily_price_data"

    def test_doge_1h_perp(self):
        assert get_collection_name("DOGE-USDT", "1h", "perp") == "doge_perp_1h_price_data"

    def test_near_daily_perp(self):
        assert get_collection_name("NEAR-USDT", "1d", "perp") == "near_perp_daily_price_data"


# ---------------------------------------------------------------------------
# get_funding_collection_name
# ---------------------------------------------------------------------------

class TestGetFundingCollectionName:
    def test_btc(self):
        assert get_funding_collection_name("BTC-USDT") == "btc_funding_rate_data"

    def test_eth(self):
        assert get_funding_collection_name("ETH-USDT") == "eth_funding_rate_data"

    def test_sol(self):
        assert get_funding_collection_name("SOL-USDT") == "sol_funding_rate_data"

    def test_doge(self):
        assert get_funding_collection_name("DOGE-USDT") == "doge_funding_rate_data"


# ---------------------------------------------------------------------------
# PERP_SYMBOL_MAP
# ---------------------------------------------------------------------------

class TestPerpSymbolMap:
    def test_btc_mapping(self):
        assert PERP_SYMBOL_MAP["BTC-USDT"] == "BTC/USDT:USDT"

    def test_eth_mapping(self):
        assert PERP_SYMBOL_MAP["ETH-USDT"] == "ETH/USDT:USDT"

    def test_sol_mapping(self):
        assert PERP_SYMBOL_MAP["SOL-USDT"] == "SOL/USDT:USDT"

    def test_all_tokens_present(self):
        assert len(PERP_SYMBOL_MAP) == len(TOKENS)
        for token in TOKENS:
            assert token in PERP_SYMBOL_MAP, f"{token} missing from PERP_SYMBOL_MAP"

    def test_all_values_end_with_usdt(self):
        for symbol, ccxt_fmt in PERP_SYMBOL_MAP.items():
            assert ccxt_fmt.endswith(":USDT"), f"{symbol} -> {ccxt_fmt} doesn't end with :USDT"


# ---------------------------------------------------------------------------
# MARKET_TYPES
# ---------------------------------------------------------------------------

class TestMarketTypes:
    def test_market_types(self):
        assert MARKET_TYPES == ["spot", "perp"]

    def test_spot_first(self):
        assert MARKET_TYPES[0] == "spot"

    def test_perp_second(self):
        assert MARKET_TYPES[1] == "perp"
