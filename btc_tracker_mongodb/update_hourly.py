#!/usr/bin/env python3
"""
update_hourly.py

Incremental hourly update:
1) Load the last 200 hours of price data from MongoDB.
2) Fetch the latest 1h BTC/USDT candle via Binance API.
3) Append to the price window (now 201 rows).
4) Compute all indicators over that window using `ta`.
5) Upsert only the new timestamped row into MongoDB.
"""

import os
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from skyfield.api import load  # loader

# Binance REST client
from binance.client import Client as BinanceClient

# TA indicators
from ta.trend      import SMAIndicator, EMAIndicator, MACD, IchimokuIndicator
from ta.volatility import BollingerBands, DonchianChannel
from ta.momentum   import RSIIndicator, StochRSIIndicator

# 1) Load env vars
load_dotenv()
MONGODB_URI        = os.getenv("MONGODB_URI")
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

# 2) Connect to MongoDB
client     = MongoClient(MONGODB_URI)
db         = client["btc_data"]
collection = db["1h_price_data"]

def load_last_200h_prices():
    cursor = (
        collection
        .find(
            {},
            {"_id": 0, "timestamp": 1, "Open":1, "High":1, "Low":1, "Close":1, "Volume":1}
        )
        .sort("timestamp", -1)
        .limit(200)
    )
    docs = list(cursor)
    if len(docs) < 200:
        raise RuntimeError(f"Expected 200 rows, found {len(docs)}")
    df = pd.DataFrame(docs)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)
    return df

def fetch_latest_candle():
    bc = BinanceClient(BINANCE_API_KEY, BINANCE_API_SECRET)
    k = bc.get_klines(symbol="BTCUSDT", interval=bc.KLINE_INTERVAL_1HOUR, limit=1)[0]
    ts = (
        datetime.utcfromtimestamp(k[0] // 1000)
        .replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    )
    return {
        "timestamp": ts,
        "Open":   float(k[1]),
        "High":   float(k[2]),
        "Low":    float(k[3]),
        "Close":  float(k[4]),
        "Volume": float(k[5]),
    }

def calculate_moon_cycle(df):
    """
    Fixed Skyfield usage: call load.timescale(), not load().
    """
    ts  = load.timescale()            # ← here
    eph = load("de421.bsp")
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
    df.loc[df["HDPR_Distance"] > threshold/100, "HDPR_Signal"] = -1
    df.loc[df["HDPR_Distance"] < -threshold/100, "HDPR_Signal"] =  1

def main():
    # 1) Load last 200h
    df = load_last_200h_prices()

    # 2) Fetch newest candle
    new = fetch_latest_candle()
    newest_ts = new["timestamp"]
    if newest_ts <= df.index.max():
        print(f"No new candle (latest ts = {newest_ts}).")
        return

    df = pd.concat([df, pd.DataFrame([new]).set_index("timestamp")])

    # 3) Compute indicators on 201-row window
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

    # 4) Extract just the new row
    new_row = df.loc[newest_ts]

    # 5) Drop if NaNs remain in numeric indicators
    numeric = [
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
    if new_row[numeric].isna().any():
        print("Skipping upsert: NaNs in long-window indicators.")
        return

    # 6) Upsert new document
    doc = new_row.to_dict()
    doc["timestamp"] = newest_ts
    collection.update_one(
        {"timestamp": newest_ts},
        {"$set": doc},
        upsert=True
    )

    print(f"✅ Upserted candle @ {newest_ts}")

if __name__ == "__main__":
    main()
