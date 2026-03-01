"""
sentiment.py — Fetch the Crypto Fear & Greed Index.

Free API at https://api.alternative.me/fng/ — no signup or API key required.
Returns a daily sentiment score (0-100) and classification string.
"""

import requests


FNG_URL = "https://api.alternative.me/fng/?limit=1&format=json"
FNG_TIMEOUT = 10  # seconds


def fetch_fear_greed() -> dict | None:
    """Fetch the latest Fear & Greed Index value.

    Returns:
        {"FnG_Value": int, "FnG_Class": str} on success,
        None if the API is unreachable or returns bad data.
    """
    try:
        resp = requests.get(FNG_URL, timeout=FNG_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        entry = data["data"][0]
        return {
            "FnG_Value": int(entry["value"]),
            "FnG_Class": str(entry["value_classification"]),
        }
    except Exception as e:
        print(f"[sentiment] Fear & Greed fetch failed (non-blocking): {e}")
        return None
