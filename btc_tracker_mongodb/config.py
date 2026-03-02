"""
config.py — Central configuration for the multi-token price tracker.
"""

TOKENS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "BNB-USDT"]

# internal name -> KuCoin API candle type
TIMEFRAMES = {"1h": "1hour", "4h": "4hour", "1d": "1day"}

DB_NAME = "btc_data"
DB_NAME_TEST = "btc_data_test"

SLIDING_WINDOW = 200
SEED_WINDOW = 500

KUCOIN_BASE = "https://api.kucoin.com"

METADATA_COLLECTION = "indicator_metadata"


def get_collection_name(symbol: str, timeframe: str) -> str:
    """Map symbol + timeframe to a collection name.

    Examples:
        'BTC-USDT' + '1h'  -> 'btc_1h_price_data'
        'ETH-USDT' + '4h'  -> 'eth_4h_price_data'
        'SOL-USDT' + '1d'  -> 'sol_daily_price_data'
    """
    token = symbol.split("-")[0].lower()
    tf_map = {"1h": "1h", "4h": "4h", "1d": "daily"}
    return f"{token}_{tf_map[timeframe]}_price_data"


def get_db_name(test: bool = False) -> str:
    return DB_NAME_TEST if test else DB_NAME
