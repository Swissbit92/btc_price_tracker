"""
config.py — Central configuration for the multi-token price tracker.
"""

TOKENS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "BNB-USDT",
          "DOGE-USDT", "AVAX-USDT", "LINK-USDT", "ADA-USDT", "SUI-USDT",
          "TON-USDT", "DOT-USDT", "NEAR-USDT",
          "PEPE-USDT", "WIF-USDT", "SHIB-USDT", "WLD-USDT", "ARB-USDT"]

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
TOKEN_METADATA_COLLECTION = "token_metadata"

# ---------------------------------------------------------------------------
# Per-token metadata (synced to MongoDB token_metadata collection)
# ---------------------------------------------------------------------------

TOKEN_METADATA = {
    "BTC-USDT": {
        "name": "Bitcoin",
        "exchange": "kucoin",
        "perp_contract": "XBTUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w", "1h"], "perp": ["1d", "1h"], "funding": ["8h"]},
    },
    "ETH-USDT": {
        "name": "Ethereum",
        "exchange": "kucoin",
        "perp_contract": "ETHUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "SOL-USDT": {
        "name": "Solana",
        "exchange": "kucoin",
        "perp_contract": "SOLUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "XRP-USDT": {
        "name": "XRP",
        "exchange": "kucoin",
        "perp_contract": "XRPUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "BNB-USDT": {
        "name": "BNB",
        "exchange": "kucoin",
        "perp_contract": "BNBUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "DOGE-USDT": {
        "name": "Dogecoin",
        "exchange": "kucoin",
        "perp_contract": "DOGEUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "AVAX-USDT": {
        "name": "Avalanche",
        "exchange": "kucoin",
        "perp_contract": "AVAXUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "LINK-USDT": {
        "name": "Chainlink",
        "exchange": "kucoin",
        "perp_contract": "LINKUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "ADA-USDT": {
        "name": "Cardano",
        "exchange": "kucoin",
        "perp_contract": "ADAUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "SUI-USDT": {
        "name": "Sui",
        "exchange": "kucoin",
        "perp_contract": "SUIUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "TON-USDT": {
        "name": "Toncoin",
        "exchange": "kucoin",
        "perp_contract": "TONUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "DOT-USDT": {
        "name": "Polkadot",
        "exchange": "kucoin",
        "perp_contract": "DOTUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "NEAR-USDT": {
        "name": "NEAR Protocol",
        "exchange": "kucoin",
        "perp_contract": "NEARUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "PEPE-USDT": {
        "name": "Pepe",
        "exchange": "kucoin",
        "perp_contract": "PEPEUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "WIF-USDT": {
        "name": "dogwifhat",
        "exchange": "kucoin",
        "perp_contract": "WIFUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "SHIB-USDT": {
        "name": "Shiba Inu",
        "exchange": "kucoin",
        "perp_contract": "SHIBUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "WLD-USDT": {
        "name": "Worldcoin",
        "exchange": "kucoin",
        "perp_contract": "WLDUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
    "ARB-USDT": {
        "name": "Arbitrum",
        "exchange": "kucoin",
        "perp_contract": "ARBUSDTM",
        "market_types": ["spot", "perp", "funding"],
        "timeframes": {"spot": ["1d", "1w"], "perp": ["1d"], "funding": ["8h"]},
    },
}

# ---------------------------------------------------------------------------
# Timeframe glossary (synced alongside token metadata)
# ---------------------------------------------------------------------------

TIMEFRAME_GLOSSARY = {
    "1d": {
        "name": "Daily",
        "interval": "24 hours",
        "description": "One candle per calendar day (UTC midnight close)",
        "production": True,
        "market_types": ["spot", "perp"],
    },
    "1w": {
        "name": "Weekly",
        "interval": "7 days",
        "description": "One candle per week (Monday open to Sunday close, UTC)",
        "production": True,
        "market_types": ["spot"],
    },
    "1h": {
        "name": "Hourly",
        "interval": "1 hour",
        "description": "One candle per hour. All 18 tokens (spot + perp) in production.",
        "production": True,
        "market_types": ["spot", "perp"],
    },
    "4h": {
        "name": "4-Hour",
        "interval": "4 hours",
        "description": "One candle per 4 hours. Not in production — re-populate via backfill when needed.",
        "production": False,
        "market_types": ["spot", "perp"],
    },
    "8h": {
        "name": "8-Hour (Funding)",
        "interval": "8 hours",
        "description": "Funding rate settlement interval. 3x per day at 00:00, 08:00, 16:00 UTC.",
        "production": True,
        "market_types": ["funding"],
    },
}


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
