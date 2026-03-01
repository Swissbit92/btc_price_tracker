"""
indicators.py — Single source of truth for ALL technical indicator computation.

Accepts an OHLCV DataFrame (columns: Open, High, Low, Close, Volume),
returns the same DataFrame enriched with indicator columns.
"""

import numpy as np
import pandas as pd
import pandas_ta_classic as ta


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Compute every indicator on the OHLCV DataFrame (in-place + return).

    The DataFrame index must be a DatetimeIndex (UTC).
    Requires columns: Open, High, Low, Close, Volume.
    """
    _compute_moving_averages(df)
    _compute_momentum(df)
    _compute_volatility_bands(df)
    _compute_ichimoku(df)
    _compute_macd(df)
    _compute_donchian(df)
    _compute_atr(df)
    _compute_adx(df)
    _compute_vwap(df)
    _compute_williams_r(df)
    _compute_cci(df)
    _compute_roc(df)
    _compute_log_returns(df)
    _compute_parkinson_volatility(df)
    _compute_realized_volatility(df)
    _compute_volatility_ratio(df)
    _compute_fibonacci(df)
    _compute_hdpr(df)
    _compute_temporal_features(df)
    return df


def get_numeric_cols() -> list[str]:
    """Column names used for NaN validation (all numeric indicator columns)."""
    return [
        # Moving averages
        "SMA_50", "SMA_100", "SMA_200",
        "EMA_20", "EMA_50", "EMA_100", "EMA_200",
        # Momentum
        "RSI", "Stoch_RSI", "Stoch_RSI_K", "Stoch_RSI_D",
        # Bollinger Bands
        "BB_High", "BB_Low",
        # Ichimoku
        "Ichimoku_Conversion", "Ichimoku_Base", "Ichimoku_A", "Ichimoku_B",
        # MACD
        "MACD_Line", "MACD_Signal", "MACD_Histogram",
        # Donchian
        "Donchian_High", "Donchian_Low", "Donchian_Mid",
        # ATR
        "ATR_14",
        # ADX
        "ADX_14", "DI_Plus_14", "DI_Minus_14",
        # VWAP
        "VWAP",
        # Williams %R
        "Williams_R_14",
        # CCI
        "CCI_20",
        # ROC
        "ROC_12", "ROC_24",
        # Log returns
        "LogReturn_1", "LogReturn_4", "LogReturn_12", "LogReturn_24",
        # Parkinson volatility
        "Parkinson_Vol_14",
        # Realized volatility
        "Realized_Vol_14", "Realized_Vol_30",
        # Volatility ratio
        "Vol_Ratio_14_30",
        # Fibonacci
        "Fib_236", "Fib_382", "Fib_500", "Fib_618", "Fib_100",
        # HDPR
        "HDPR_MA", "HDPR_Distance", "HDPR_Signal",
        # Temporal
        "Hour_Sin", "Hour_Cos", "DOW_Sin", "DOW_Cos",
    ]


# ---------------------------------------------------------------------------
# Moving averages
# ---------------------------------------------------------------------------

def _compute_moving_averages(df: pd.DataFrame):
    df["SMA_50"]  = ta.sma(df["Close"], length=50)
    df["SMA_100"] = ta.sma(df["Close"], length=100)
    df["SMA_200"] = ta.sma(df["Close"], length=200)
    df["EMA_20"]  = ta.ema(df["Close"], length=20)
    df["EMA_50"]  = ta.ema(df["Close"], length=50)
    df["EMA_100"] = ta.ema(df["Close"], length=100)
    df["EMA_200"] = ta.ema(df["Close"], length=200)


# ---------------------------------------------------------------------------
# Momentum
# ---------------------------------------------------------------------------

def _compute_momentum(df: pd.DataFrame):
    df["RSI"] = ta.rsi(df["Close"], length=14)

    stoch_rsi = ta.stochrsi(df["Close"], length=14, rsi_length=14, k=3, d=3)
    if stoch_rsi is not None and not stoch_rsi.empty:
        cols = stoch_rsi.columns.tolist()
        # pandas_ta returns [0,100]; normalize to [0,1] for compatibility with old pipeline
        df["Stoch_RSI"]   = stoch_rsi[cols[0]] / 100
        df["Stoch_RSI_K"] = stoch_rsi[cols[0]] / 100
        df["Stoch_RSI_D"] = stoch_rsi[cols[1]] / 100


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def _compute_volatility_bands(df: pd.DataFrame):
    bb = ta.bbands(df["Close"], length=20, std=2)
    if bb is not None and not bb.empty:
        cols = bb.columns.tolist()
        # pandas_ta bbands returns: BBL, BBM, BBU, BBB, BBP
        df["BB_Low"]  = bb[cols[0]]
        df["BB_High"] = bb[cols[2]]


# ---------------------------------------------------------------------------
# Ichimoku
# ---------------------------------------------------------------------------

def _compute_ichimoku(df: pd.DataFrame):
    ichi = ta.ichimoku(df["High"], df["Low"], df["Close"],
                       tenkan=9, kijun=26, senkou=52)
    if ichi is not None and isinstance(ichi, tuple) and len(ichi) >= 1:
        ichi_df = ichi[0]
        cols = ichi_df.columns.tolist()
        # Returns: ISA_9, ISB_26, ITS_9, IKS_26, ICS_26
        for col in cols:
            if "ITS" in col:
                df["Ichimoku_Conversion"] = ichi_df[col]
            elif "IKS" in col:
                df["Ichimoku_Base"] = ichi_df[col]
            elif "ISA" in col:
                df["Ichimoku_A"] = ichi_df[col]
            elif "ISB" in col:
                df["Ichimoku_B"] = ichi_df[col]


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def _compute_macd(df: pd.DataFrame):
    macd = ta.macd(df["Close"], fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        cols = macd.columns.tolist()
        # Returns: MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
        for col in cols:
            if col.startswith("MACDh"):
                df["MACD_Histogram"] = macd[col]
            elif col.startswith("MACDs"):
                df["MACD_Signal"] = macd[col]
            elif col.startswith("MACD"):
                df["MACD_Line"] = macd[col]


# ---------------------------------------------------------------------------
# Donchian Channel
# ---------------------------------------------------------------------------

def _compute_donchian(df: pd.DataFrame):
    don = ta.donchian(df["High"], df["Low"], lower_length=20, upper_length=20)
    if don is not None and not don.empty:
        cols = don.columns.tolist()
        # Returns: DCL_20_20, DCM_20_20, DCU_20_20
        for col in cols:
            if col.startswith("DCL"):
                df["Donchian_Low"] = don[col]
            elif col.startswith("DCM"):
                df["Donchian_Mid"] = don[col]
            elif col.startswith("DCU"):
                df["Donchian_High"] = don[col]


# ---------------------------------------------------------------------------
# ATR (Average True Range)
# ---------------------------------------------------------------------------

def _compute_atr(df: pd.DataFrame):
    df["ATR_14"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)


# ---------------------------------------------------------------------------
# ADX (Average Directional Index) + DI+/DI-
# ---------------------------------------------------------------------------

def _compute_adx(df: pd.DataFrame):
    adx = ta.adx(df["High"], df["Low"], df["Close"], length=14)
    if adx is not None and not adx.empty:
        cols = adx.columns.tolist()
        for col in cols:
            if col.startswith("ADX"):
                df["ADX_14"] = adx[col]
            elif col.startswith("DMP"):
                df["DI_Plus_14"] = adx[col]
            elif col.startswith("DMN"):
                df["DI_Minus_14"] = adx[col]


# ---------------------------------------------------------------------------
# VWAP (Volume Weighted Average Price)
# ---------------------------------------------------------------------------

def _compute_vwap(df: pd.DataFrame):
    # Manual cumulative VWAP — avoids pandas_ta timezone warnings
    # and works correctly for 24/7 crypto markets
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    df["VWAP"] = (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()


# ---------------------------------------------------------------------------
# Williams %R
# ---------------------------------------------------------------------------

def _compute_williams_r(df: pd.DataFrame):
    df["Williams_R_14"] = ta.willr(df["High"], df["Low"], df["Close"], length=14)


# ---------------------------------------------------------------------------
# CCI (Commodity Channel Index)
# ---------------------------------------------------------------------------

def _compute_cci(df: pd.DataFrame):
    df["CCI_20"] = ta.cci(df["High"], df["Low"], df["Close"], length=20)


# ---------------------------------------------------------------------------
# ROC (Rate of Change)
# ---------------------------------------------------------------------------

def _compute_roc(df: pd.DataFrame):
    df["ROC_12"] = ta.roc(df["Close"], length=12)
    df["ROC_24"] = ta.roc(df["Close"], length=24)


# ---------------------------------------------------------------------------
# Log Returns
# ---------------------------------------------------------------------------

def _compute_log_returns(df: pd.DataFrame):
    log_close = np.log(df["Close"])
    df["LogReturn_1"]  = log_close.diff(1)
    df["LogReturn_4"]  = log_close.diff(4)
    df["LogReturn_12"] = log_close.diff(12)
    df["LogReturn_24"] = log_close.diff(24)


# ---------------------------------------------------------------------------
# Parkinson Volatility (14-period rolling)
# ---------------------------------------------------------------------------

def _compute_parkinson_volatility(df: pd.DataFrame):
    log_hl = np.log(df["High"] / df["Low"])
    df["Parkinson_Vol_14"] = np.sqrt(
        (1 / (4 * np.log(2))) * (log_hl ** 2).rolling(14).mean()
    )


# ---------------------------------------------------------------------------
# Realized Volatility (14 and 30-period rolling)
# ---------------------------------------------------------------------------

def _compute_realized_volatility(df: pd.DataFrame):
    log_ret = np.log(df["Close"] / df["Close"].shift(1))
    df["Realized_Vol_14"] = log_ret.rolling(14).std() * np.sqrt(14)
    df["Realized_Vol_30"] = log_ret.rolling(30).std() * np.sqrt(30)


# ---------------------------------------------------------------------------
# Volatility Ratio (14/30 — regime signal)
# ---------------------------------------------------------------------------

def _compute_volatility_ratio(df: pd.DataFrame):
    if "Realized_Vol_14" in df.columns and "Realized_Vol_30" in df.columns:
        df["Vol_Ratio_14_30"] = df["Realized_Vol_14"] / df["Realized_Vol_30"]


# ---------------------------------------------------------------------------
# Fibonacci Retracement (rolling 50-period window)
# ---------------------------------------------------------------------------

def _compute_fibonacci(df: pd.DataFrame):
    window = 50
    rolling_high = df["High"].rolling(window).max()
    rolling_low  = df["Low"].rolling(window).min()
    diff = rolling_high - rolling_low
    df["Fib_236"] = rolling_high - 0.236 * diff
    df["Fib_382"] = rolling_high - 0.382 * diff
    df["Fib_500"] = rolling_high - 0.5   * diff
    df["Fib_618"] = rolling_high - 0.618 * diff
    df["Fib_100"] = rolling_low


# ---------------------------------------------------------------------------
# HDPR (High Distance Price Reversal) — custom mean-reversion signal
# ---------------------------------------------------------------------------

def _compute_hdpr(df: pd.DataFrame, ma_window: int = 50, threshold: float = 3.0):
    df["HDPR_MA"]       = df["Close"].rolling(ma_window).mean()
    df["HDPR_Distance"] = (df["Close"] - df["HDPR_MA"]) / df["HDPR_MA"]
    df["HDPR_Signal"]   = 0
    df.loc[df["HDPR_Distance"] >  threshold / 100, "HDPR_Signal"] = -1
    df.loc[df["HDPR_Distance"] < -threshold / 100, "HDPR_Signal"] =  1


# ---------------------------------------------------------------------------
# Temporal features (cyclical encoding)
# ---------------------------------------------------------------------------

def _compute_temporal_features(df: pd.DataFrame):
    hours = df.index.hour
    days  = df.index.dayofweek
    df["Hour_Sin"] = np.sin(2 * np.pi * hours / 24)
    df["Hour_Cos"] = np.cos(2 * np.pi * hours / 24)
    df["DOW_Sin"]  = np.sin(2 * np.pi * days / 7)
    df["DOW_Cos"]  = np.cos(2 * np.pi * days / 7)
