#!/usr/bin/env python3
"""
update_daily.py

1) Load last daily timestamp from MongoDB.
2) If today at 00:00 UTC is greater, backfill missing 1-day candles via KuCoin.
3) Compute indicators on extended daily window.
4) Upsert each new daily document.
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from skyfield.api import load as sf_load

# TA indicators (same as seed)
from ta.trend      import SMAIndicator, EMAIndicator, MACD, IchimokuIndicator
from ta.volatility import BollingerBands, DonchianChannel
from ta.momentum   import RSIIndicator, StochRSIIndicator

# 1) Load env vars
load_dotenv()
MONGODB_URI       = os.getenv("MONGODB_URI")
KUCOIN_API_KEY    = os.getenv("KUCOIN_API_KEY")
KUCOIN_API_SECRET = os.getenv("KUCOIN_API_SECRET")
KUCOIN_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")

# 2) Connect to MongoDB daily collection
client           = MongoClient(MONGODB_URI)
db               = client["btc_data"]
daily_collection = db["daily_price_data"]

# KuCoin API
KUCOIN_BASE = "https://api.kucoin.com"

def load_last_daily_timestamp() -> datetime:
    """
    Fetch the most recent daily document's timestamp from MongoDB.
    """
    doc = daily_collection.find_one(
        {}, {"_id":0, "timestamp":1}
    , sort=[("timestamp", -1)])
    if not doc:
        raise RuntimeError("No daily docs found; run seed_daily.py first.")
    return pd.to_datetime(doc["timestamp"], utc=True)

def fetch_missing_daily(start_ts: int, end_ts: int):
    """
    Fetch all 1-day BTC-USDT candles from KuCoin between start_ts & end_ts (unix seconds).
    """
    params = {
        "symbol":  "BTC-USDT",
        "type":    "1day",
        "startAt": start_ts,
        "endAt":   end_ts
    }
    r = requests.get(f"{KUCOIN_BASE}/api/v1/market/candles", params=params)
    r.raise_for_status()
    data = r.json().get("data", [])
    candles = []
    for entry in data:
        t, o, c, h, l, v, _ = entry
        dt = datetime.fromtimestamp(int(t), tz=timezone.utc)\
                     .replace(hour=0, minute=0, second=0, microsecond=0)
        candles.append({
            "timestamp": dt,
            "Open":   float(o),
            "High":   float(h),
            "Low":    float(l),
            "Close":  float(c),
            "Volume": float(v),
        })
    return candles

def calculate_moon_cycle(df: pd.DataFrame):
    ts  = sf_load.timescale()
    eph = sf_load("de421.bsp")
    earth, moon, sun = eph["earth"], eph["moon"], eph["sun"]
    phases = []
    for dt in df.index:
        t = ts.utc(dt.year, dt.month, dt.day)
        angle = earth.at(t).observe(moon).apparent().phase_angle(sun).degrees % 360
        if angle < 45:      phases.append("New Moon")
        elif angle < 135:   phases.append("First Quarter")
        elif angle < 225:   phases.append("Full Moon")
        else:               phases.append("Last Quarter")
    df["Moon_Cycle"] = phases

def calculate_fibonacci(df: pd.DataFrame):
    low, high = df["Low"].min(), df["High"].max()
    diff = high - low
    df["Fib_0.236"] = high - 0.236 * diff
    df["Fib_0.382"] = high - 0.382 * diff
    df["Fib_0.5"]   = high - 0.5   * diff
    df["Fib_0.618"] = high - 0.618 * diff
    df["Fib_1.0"]   = low

def calculate_hdpr(df: pd.DataFrame, ma_window=50, threshold=3.0):
    df["HDPR_MA"]       = df["Close"].rolling(ma_window).mean()
    df["HDPR_Distance"] = (df["Close"] - df["HDPR_MA"]) / df["HDPR_MA"]
    df["HDPR_Signal"]   = 0
    df.loc[df["HDPR_Distance"] >  threshold/100, "HDPR_Signal"] = -1
    df.loc[df["HDPR_Distance"] < -threshold/100, "HDPR_Signal"] =  1

def main():
    # 1) Load last daily timestamp
    last_dt = load_last_daily_timestamp()

    # 2) Compute today@00:00 UTC
    now_dt = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if now_dt <= last_dt:
        print(f"No new daily bars—latest is {last_dt.date()}.")
        return

    # 3) Fetch missing days from last_dt+1 to now_dt
    start_unix = int((last_dt + timedelta(days=1)).timestamp())
    end_unix   = int(now_dt.timestamp())
    missing = fetch_missing_daily(start_unix, end_unix)
    if not missing:
        print(f"No missing daily candles between {last_dt.date()} and {now_dt.date()}.")
        return

    # 4) Sort ascending and build a DataFrame for indicator calculation
    missing.sort(key=lambda x: x["timestamp"])
    df_missing = pd.DataFrame(missing).set_index("timestamp")

    # 5) We need a price window of at least 200 days for long indicators.
    #    Load the last 200 daily docs:
    cursor = (
        daily_collection
        .find({}, {"_id":0, "timestamp":1, "Open":1, "High":1, "Low":1, "Close":1, "Volume":1})
        .sort("timestamp", -1)
        .limit(200)
    )
    existing_docs = list(cursor)
    df_existing = pd.DataFrame(existing_docs)
    df_existing["timestamp"] = pd.to_datetime(df_existing["timestamp"], utc=True)
    df_existing = df_existing.set_index("timestamp").sort_index()

    # 6) Concatenate existing + missing to form the extended window
    df_full = pd.concat([df_existing, df_missing])

    # 7) Compute indicators on df_full
    df_full["SMA_50"]  = SMAIndicator(df_full["Close"], window=50).sma_indicator()
    df_full["SMA_100"] = SMAIndicator(df_full["Close"], window=100).sma_indicator()
    df_full["SMA_200"] = SMAIndicator(df_full["Close"], window=200).sma_indicator()

    df_full["EMA_20"]  = EMAIndicator(df_full["Close"], window=20).ema_indicator()
    df_full["EMA_50"]  = EMAIndicator(df_full["Close"], window=50).ema_indicator()
    df_full["EMA_100"] = EMAIndicator(df_full["Close"], window=100).ema_indicator()
    df_full["EMA_200"] = EMAIndicator(df_full["Close"], window=200).ema_indicator()

    df_full["RSI"] = RSIIndicator(df_full["Close"], window=14).rsi()
    st = StochRSIIndicator(df_full["Close"], window=14, smooth1=3, smooth2=3)
    df_full["Stoch_RSI"]   = st.stochrsi()
    df_full["Stoch_RSI_K"] = st.stochrsi_k()
    df_full["Stoch_RSI_D"] = st.stochrsi_d()

    bb = BollingerBands(df_full["Close"], window=20, window_dev=2)
    df_full["BB_High"] = bb.bollinger_hband()
    df_full["BB_Low"]  = bb.bollinger_lband()

    ich = IchimokuIndicator(
        high=df_full["High"], low=df_full["Low"],
        window1=9, window2=26, window3=52
    )
    df_full["Ichimoku_Conversion"] = ich.ichimoku_conversion_line()
    df_full["Ichimoku_Base"]       = ich.ichimoku_base_line()
    df_full["Ichimoku_A"]          = ich.ichimoku_a()
    df_full["Ichimoku_B"]          = ich.ichimoku_b()

    don = DonchianChannel(
        high=df_full["High"], low=df_full["Low"],
        close=df_full["Close"], window=20
    )
    df_full["Donchian_High"] = don.donchian_channel_hband()
    df_full["Donchian_Low"]  = don.donchian_channel_lband()
    df_full["Donchian_Mid"]  = don.donchian_channel_mband()

    calculate_fibonacci(df_full)
    calculate_moon_cycle(df_full)
    calculate_hdpr(df_full)

    macd = MACD(df_full["Close"], window_slow=26, window_fast=12, window_sign=9)
    df_full["MACD_Line"]      = macd.macd()
    df_full["MACD_Signal"]    = macd.macd_signal()
    df_full["MACD_Histogram"] = macd.macd_diff()

    # 8) Upsert each missing day in timestamp order
    numeric_cols = [
        "SMA_50","SMA_100","SMA_200",
        "EMA_20","EMA_50","EMA_100","EMA_200",
        "RSI","Stoch_RSI","Stoch_RSI_K","Stoch_RSI_D",
        "BB_High","BB_Low",
        "Ichimoku_Conversion","Ichimoku_Base","Ichimoku_A","Ichimoku_B",
        "Donchian_High","Donchian_Low","Donchian_Mid",
        "Fib_0.236","Fib_0.382","Fib_0.5","Fib_0.618","Fib_1.0",
        "HDPR_MA","HDPR_Distance","HDPR_Signal",
        "MACD_Line","MACD_Signal","MACD_Histogram"
    ]
    for ts in df_missing.index:
        row = df_full.loc[ts]
        if row[numeric_cols].isna().any():
            print(f"Skipping {ts.date()}: NaNs in indicators.")
            continue
        doc = row.to_dict()
        doc["timestamp"] = ts
        daily_collection.update_one(
            {"timestamp": ts},
            {"$set": doc},
            upsert=True
        )
        print(f"✅ Upserted daily candle @ {ts.date()}")

if __name__ == "__main__":
    main()
