#!/usr/bin/env python3
"""
seed_daily.py

1) Read historical daily CSV (skipping the extra header row).
2) Compute all TA indicators.
3) Drop rows with NaN in numeric indicators.
4) Upsert into MongoDB 'daily_price_data' collection in descending order.
"""

import os
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from skyfield.api import load as sf_load  # for moon phases

# TA indicators
from ta.trend      import SMAIndicator, EMAIndicator, MACD, IchimokuIndicator
from ta.volatility import BollingerBands, DonchianChannel
from ta.momentum   import RSIIndicator, StochRSIIndicator

# 1) Load env vars
load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")

# 2) Connect to MongoDB
client           = MongoClient(MONGODB_URI)
db               = client["btc_data"]
daily_collection = db["daily_price_data"]

def load_csv_daily(file_path: str) -> pd.DataFrame:
    """
    Read CSV that looks like (two header rows—skip the second unit row):
      Date,Close,High,Low,Open,Volume
      ,BTC-USD,BTC-USD,BTC-USD,BTC-USD,BTC-USD
      2016-01-01,434.33,436.25,427.52,430.72,36278900
      2016-01-02,...
    Returns a DataFrame indexed by midnight-UTC timestamps with numeric columns.
    """
    # Skip the second line (unit headers) by skiprows=[1]
    df = pd.read_csv(file_path, skiprows=[1], parse_dates=["Date"])

    # Convert price/volume columns to numeric (just in case)
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop any rows that failed conversion
    df.dropna(subset=["Open", "High", "Low", "Close", "Volume"], inplace=True)

    # Create a UTC-midnight timestamp column
    df["timestamp"] = (
        df["Date"]
        .dt.tz_localize("UTC")
        .apply(lambda dt: dt.replace(hour=0, minute=0, second=0, microsecond=0))
    )

    # Set index and keep only OHLCV
    df = df.set_index("timestamp")[["Open", "High", "Low", "Close", "Volume"]]
    return df

def calculate_moon_cycle(df: pd.DataFrame):
    ts  = sf_load.timescale()
    eph = sf_load("de421.bsp")
    earth, moon, sun = eph["earth"], eph["moon"], eph["sun"]

    phases = []
    for dt in df.index:
        t = ts.utc(dt.year, dt.month, dt.day)
        angle = earth.at(t).observe(moon).apparent().phase_angle(sun).degrees % 360
        if angle < 45:
            phases.append("New Moon")
        elif angle < 135:
            phases.append("First Quarter")
        elif angle < 225:
            phases.append("Full Moon")
        else:
            phases.append("Last Quarter")
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
    # 1) Load CSV file (adjust path as needed)
    csv_path = "daily_history.csv"
    df = load_csv_daily(csv_path)

    # 2) Compute all indicators
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

    ich = IchimokuIndicator(
        high=df["High"], low=df["Low"],
        window1=9, window2=26, window3=52
    )
    df["Ichimoku_Conversion"] = ich.ichimoku_conversion_line()
    df["Ichimoku_Base"]       = ich.ichimoku_base_line()
    df["Ichimoku_A"]          = ich.ichimoku_a()
    df["Ichimoku_B"]          = ich.ichimoku_b()

    don = DonchianChannel(
        high=df["High"], low=df["Low"],
        close=df["Close"], window=20
    )
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

    # 3) Drop rows still missing numeric indicators
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
    df.dropna(subset=numeric_cols, inplace=True)

    # 4) Sort descending (newest first)
    df = df.sort_index(ascending=False)

    # 5) Upsert into 'daily_price_data'
    for ts, row in df.iterrows():
        doc = row.to_dict()
        doc["timestamp"] = ts
        daily_collection.update_one(
            {"timestamp": ts},
            {"$set": doc},
            upsert=True
        )

    print(f"✅ Seeded {len(df)} daily candles with indicators (newest first)")

if __name__ == "__main__":
    main()
