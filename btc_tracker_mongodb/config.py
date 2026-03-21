"""
config.py — Central configuration for the multi-token price tracker.
"""

TOKENS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "BNB-USDT",
          "DOGE-USDT", "AVAX-USDT", "LINK-USDT", "ADA-USDT", "SUI-USDT",
          "TON-USDT", "DOT-USDT", "NEAR-USDT"]

# internal name -> KuCoin API candle type
TIMEFRAMES = {"1h": "1hour", "4h": "4hour", "1d": "1day", "1w": "1week"}

MARKET_TYPES = ["spot", "perp"]

# KuCoin Futures contract symbols in CCXT unified format (BTC/USDT:USDT)
# Native KuCoin names: XBTUSDTM, ETHUSDTM, etc.
PERP_SYMBOL_MAP = {sym: sym.replace("-", "/") + ":USDT" for sym in TOKENS}

DB_NAME = "btc_data"
DB_NAME_TEST = "btc_data_test"

SLIDING_WINDOW = 200
SEED_WINDOW = 500

KUCOIN_BASE = "https://api.kucoin.com"

METADATA_COLLECTION = "indicator_glossary"
FUNDING_METADATA_COLLECTION = "funding_rate_glossary"


def get_collection_name(symbol: str, timeframe: str, market_type: str = "spot") -> str:
    """Map symbol + timeframe + market type to a collection name.

    Examples:
        'BTC-USDT' + '1h' + 'spot' -> 'btc_1h_price_data'
        'ETH-USDT' + '4h' + 'perp' -> 'eth_perp_4h_price_data'
        'SOL-USDT' + '1d' + 'spot' -> 'sol_daily_price_data'
        'SOL-USDT' + '1d' + 'perp' -> 'sol_perp_daily_price_data'
    """
    token = symbol.split("-")[0].lower()
    tf_map = {"1h": "1h", "4h": "4h", "1d": "daily", "1w": "weekly"}
    if market_type == "perp":
        return f"{token}_perp_{tf_map[timeframe]}_price_data"
    return f"{token}_{tf_map[timeframe]}_price_data"


def get_funding_collection_name(symbol: str) -> str:
    """Map symbol to a funding rate collection name.

    Funding rate collections are per-token (not per-timeframe) because
    funding settlements are always on an 8h schedule regardless of OHLCV timeframe.

    Examples:
        'BTC-USDT' -> 'btc_funding_rate_data'
        'ETH-USDT' -> 'eth_funding_rate_data'
    """
    token = symbol.split("-")[0].lower()
    return f"{token}_funding_rate_data"


def get_db_name(test: bool = False) -> str:
    return DB_NAME_TEST if test else DB_NAME
