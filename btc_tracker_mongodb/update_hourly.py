#!/usr/bin/env python3
"""
update_hourly.py

Robust hourly update via KuCoin with backfill:
1) Load the last 200 hours of price data from MongoDB.
2) Determine how many hours are missing (if any).
3) Fetch all missing 1h candles via KuCoin public API.
4) Append to the sliding window, recompute indicators once.
5) Upsert each newly fetched candle in timestamp order.
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from skyfield.api import load as sf_load

# TA indicators
from ta.trend      import SMAIndicator, EMAIndicator, MACD, IchimokuIndicator
from ta.volatility import BollingerBands, DonchianChannel
from ta.momentum   import RSIIndicator, StochRSIIndicator

# 1) Load env vars
load_dotenv()
MONGODB_URI      = os.getenv("MONGODB_URI")
KUCOIN_API_KEY    = os.getenv("KUCOIN_API_KEY")
KUCOIN_API_SECRET = os.getenv("KUCOIN_API_SECRET")
KUCOIN_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")

# 2) Connect to MongoDB
client     = MongoClient(MONGODB_URI)
db         = client["btc_data"]
collection = db["1h_price_data"]

# KuCoin base URL
KUCOIN_BASE = "https://api.kucoin.com"

def load_last_200h_prices():
    """Load the last 200 hourly candles from MongoDB, sorted ascending."""
    cursor = (
        collection
        .find(
            {},
            {"_id":0, "timestamp":1, "Open":1, "High":1, "Low":1, "Close":1, "Volume":1}
        )
        .sort("timestamp", -1)
        .limit(200)
    )
    docs = list(cursor)
    if len(docs) < 200:
        raise RuntimeError(f"Expected 200 rows, found {len(docs)} in MongoDB.")
    df = pd.DataFrame(docs)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)
    return df

def fetch_missing_candles(start_ts: int, end_ts: int):
    """
    Fetch all 1h BTC-USDT candles from KuCoin between start_ts and end_ts (unix seconds).
    Returns list of dicts with timestamp, Open, High, Low, Close, Volume.
    """
    params = {
        "symbol":  "BTC-USDT",
        "type":    "1hour",
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
                     .replace(minute=0, second=0, microsecond=0)
        candles.append({
            "timestamp": dt,
            "Open":   float(o),
            "High":   float(h),
            "Low":    float(l),
            "Close":  float(c),
            "Volume": float(v),
        })
    return candles

def calculate_moon_cycle(df):
    ts  = sf_load.timescale()
    eph = sf_load("de421.bsp")
    earth, moon, sun = eph["earth"], eph["moon"], eph["sun"]

    phases = []
    for dt in df.index:
        t = ts.utc(dt.year, dt.month, dt.day, dt.hour)
        angle = earth.at(t).observe(moon).apparent().phase_angle(sun).degrees % 360
        if   angle < 45:  phases.append("New Moon")
        elif angle < 135: phases.append("First Quarter")
        elif angle < 225: phases.append("Full Moon")
        else:             phases.append("Last Quarter")
    df["Moon_Cycle"] = phases

def calculate_fibonacci(df):
    low, high = df["Low"].min(), df["High"].max()
    diff = high - low
    df["Fib_0.236"] = high - 0.236 * diff
    df["Fib_0.382"] = high - 0.382 * diff
    df["Fib_0.5"]   = high - 0.5   * diff
    df["Fib_0.618"] = high - 0.618 * diff
    df["Fib_1.0"]   = low

def calculate_hdpr(df, ma_window=50, threshold=3.0):
    df["HDPR_MA"]       = df["Close"].rolling(ma_window).mean()
    df["HDPR_Distance"] = (df["Close"] - df["HDPR_MA"]) / df["HDPR_MA"]
    df["HDPR_Signal"]   = 0
    df.loc[df["HDPR_Distance"] >  threshold/100, "HDPR_Signal"] = -1
    df.loc[df["HDPR_Distance"] < -threshold/100, "HDPR_Signal"] =  1

def main():
    # 1) Load last 200h window
    df = load_last_200h_prices()
    last_ts = df.index.max()

    # 2) Determine current top-of-hour
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if now <= last_ts:
        print(f"No new candles—latest in DB is {last_ts}")
        return

    # 3) Backfill: fetch all missing hours between last_ts+1h and now
    start_unix = int((last_ts + timedelta(hours=1)).timestamp())
    end_unix   = int(now.timestamp())
    missing = fetch_missing_candles(start_unix, end_unix)

    if not missing:
        print(f"No missing candles found between {last_ts} and {now}")
        return

    # 4) Sort ascending by timestamp and append to DataFrame
    missing.sort(key=lambda x: x["timestamp"])
    df_missing = pd.DataFrame(missing).set_index("timestamp")
    df = pd.concat([df, df_missing])

    # 5) Recompute all indicators on the extended window
    df["SMA_50"]  = SMAIndicator(df["Close"], window=50).sma_indicator()
    df["SMA_100"] = SMAIndicator(df["Close"], window=100).sma_indicator()
    df["SMA_200"] = SMAIndicator(df["Close"], window=200).sma_indicator()

    df["EMA_20"]  = EMAIndicator(df["Close"], window=20).ema_indicator()
    df["EMA_50"]  = EMAIndicator(df["Close"], window=50).ema_indicator()
    df["EMA_100"] = EMAIndicator(df["Close"], window=100).ema_indicator()
    df["EMA_200"] = EMAIndicator(df["Close"], window=200).ema_indicator()

    df["RSI"] = RSIIndicator(df["Close"], window=14).rsi()
    st = StochRSIIndicator(df["Close"], window=14, smooth1=3, smooth2=3)
    df["Stoch_RSI"]   = st.stochrsi()
    df["Stoch_RSI_K"] = st.stochrsi_k()
    df["Stoch_RSI_D"] = st.stochrsi_d()

    bb = BollingerBands(df["Close"], window=20, window_dev=2)
    df["BB_High"] = bb.bollinger_hband()
    df["BB_Low"]  = bb.bollinger_lband()

    ich = IchimokuIndicator(high=df["High"], low=df["Low"],
                             window1=9, window2=26, window3=52)
    df["Ichimoku_Conversion"] = ich.ichimoku_conversion_line()
    df["Ichimoku_Base"]       = ich.ichimoku_base_line()
    df["Ichimoku_A"]          = ich.ichimoku_a()
    df["Ichimoku_B"]          = ich.ichimoku_b()

    don = DonchianChannel(high=df["High"], low=df["Low"],
                          close=df["Close"], window=20)
    df["Donchian_High"] = don.donchian_channel_hband()
    df["Donchian_Low"]  = don.donchian_channel_lband()
    df["Donchian_Mid"]  = don.donchian_channel_mband()

    calculate_fibonacci(df)
    calculate_moon_cycle(df)
    calculate_hdpr(df)

    macd = MACD(df["Close"], window_slow=26, window_fast=12, window_sign=9)
    df["MACD_Line"]      = macd.macd()
    df["MACD_Signal"]    = macd.macd_signal()
    df["MACD_Histogram"] = macd.macd_diff()

    # 6) Upsert each missing candle in order
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
        row = df.loc[ts]
        if row[numeric_cols].isna().any():
            print(f"Skipping {ts}: NaNs in indicators.")
            continue
        doc = row.to_dict()
        doc["timestamp"] = ts
        collection.update_one({"timestamp": ts}, {"$set": doc}, upsert=True)
        print(f"✅ Upserted backfilled candle @ {ts}")

if __name__ == "__main__":
    main()
