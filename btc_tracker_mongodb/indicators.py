"""
indicators.py — Single source of truth for ALL technical indicator computation.

Accepts an OHLCV DataFrame (columns: Open, High, Low, Close, Volume),
returns the same DataFrame enriched with indicator columns.

INDICATOR_GLOSSARY is the canonical reference for every column. When adding,
removing, or renaming an indicator, update the glossary dict below —
get_numeric_cols() derives from it automatically.  Also update the human-
readable glossary at docs/INDICATORS.md.
"""

import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pandas_ta_classic as ta


# ---------------------------------------------------------------------------
# Indicator Glossary — single source of truth for column metadata
# ---------------------------------------------------------------------------

CATEGORY_ORDER = [
    "Trend", "Momentum", "Volume", "Volatility", "Risk", "Price Levels",
    "Custom", "Log Returns", "Temporal", "ML Features", "Sentiment",
]

INDICATOR_GLOSSARY: dict[str, dict] = {
    # ── Trend ──────────────────────────────────────────────────────────────
    "SMA_50": {
        "name": "Simple Moving Average",
        "category": "Trend",
        "parameters": "50-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Average closing price over the last 50 bars. Smooths noise; acts as dynamic support/resistance.",
    },
    "SMA_100": {
        "name": "Simple Moving Average",
        "category": "Trend",
        "parameters": "100-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Medium-term trend filter. Price above = bullish bias.",
    },
    "SMA_200": {
        "name": "Simple Moving Average",
        "category": "Trend",
        "parameters": "200-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Long-term trend benchmark. The bull/bear market dividing line.",
    },
    "EMA_20": {
        "name": "Exponential Moving Average",
        "category": "Trend",
        "parameters": "20-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Fast trend tracker. Weights recent prices more than SMA.",
    },
    "EMA_50": {
        "name": "Exponential Moving Average",
        "category": "Trend",
        "parameters": "50-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Medium trend. Crossovers with EMA_20 signal momentum shifts.",
    },
    "EMA_100": {
        "name": "Exponential Moving Average",
        "category": "Trend",
        "parameters": "100-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Intermediate trend filter between 50 and 200.",
    },
    "EMA_200": {
        "name": "Exponential Moving Average",
        "category": "Trend",
        "parameters": "200-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Long-term EMA. More responsive than SMA_200 to recent data.",
    },
    "Ichimoku_Conversion": {
        "name": "Ichimoku Tenkan-sen",
        "category": "Trend",
        "parameters": "9-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Short-term midpoint: (9-period high + 9-period low) / 2. Signals short-term momentum.",
    },
    "Ichimoku_Base": {
        "name": "Ichimoku Kijun-sen",
        "category": "Trend",
        "parameters": "26-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Medium-term midpoint. Acts as support/resistance; flat = ranging market.",
    },
    "Ichimoku_A": {
        "name": "Ichimoku Senkou Span A",
        "category": "Trend",
        "parameters": "(9+26)/2",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Leading span A of the cloud. Midpoint of Conversion and Base, projected forward.",
    },
    "Ichimoku_B": {
        "name": "Ichimoku Senkou Span B",
        "category": "Trend",
        "parameters": "52-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Leading span B. Slowest cloud component; defines cloud thickness.",
    },
    "ADX_14": {
        "name": "Average Directional Index",
        "category": "Trend",
        "parameters": "14-period",
        "range": "0-100",
        "dtype": "numeric",
        "description": "Measures trend strength (not direction). <20 = weak/no trend, >25 = trending, >50 = strong trend.",
    },
    "DI_Plus_14": {
        "name": "Positive Directional Indicator",
        "category": "Trend",
        "parameters": "14-period",
        "range": "0-100",
        "dtype": "numeric",
        "description": "Measures upward movement strength. DI+ > DI- suggests bullish pressure.",
    },
    "DI_Minus_14": {
        "name": "Negative Directional Indicator",
        "category": "Trend",
        "parameters": "14-period",
        "range": "0-100",
        "dtype": "numeric",
        "description": "Measures downward movement strength. DI- > DI+ suggests bearish pressure.",
    },
    "Supertrend_Value": {
        "name": "Supertrend Line",
        "category": "Trend",
        "parameters": "length=7, mult=3.0",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "ATR-based trailing stop line. Price above = uptrend, below = downtrend.",
    },
    "Supertrend_Direction": {
        "name": "Supertrend Direction",
        "category": "Trend",
        "parameters": "length=7, mult=3.0",
        "range": "-1 or +1",
        "dtype": "numeric",
        "description": "Binary trend signal: +1 = uptrend, -1 = downtrend. Directly actionable.",
    },
    "KAMA_10": {
        "name": "Kaufman Adaptive Moving Average",
        "category": "Trend",
        "parameters": "10-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Adapts speed to volatility: fast in trends, flat in chop. Superior noise filtering vs SMA/EMA.",
    },
    "HMA_20": {
        "name": "Hull Moving Average",
        "category": "Trend",
        "parameters": "20-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Dramatically reduced lag while remaining smooth. Uses weighted MA of WMAs.",
    },
    "PSAR": {
        "name": "Parabolic SAR",
        "category": "Trend",
        "parameters": "default af/max",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Trend-following trailing stop. Dots flip above/below price on trend reversal.",
    },
    "Aroon_Up": {
        "name": "Aroon Up",
        "category": "Trend",
        "parameters": "25-period",
        "range": "0-100",
        "dtype": "numeric",
        "description": "Measures bars since highest high. 100 = new high just made, 0 = no new high in 25 bars.",
    },
    "Aroon_Down": {
        "name": "Aroon Down",
        "category": "Trend",
        "parameters": "25-period",
        "range": "0-100",
        "dtype": "numeric",
        "description": "Measures bars since lowest low. 100 = new low just made.",
    },
    "Aroon_Osc": {
        "name": "Aroon Oscillator",
        "category": "Trend",
        "parameters": "25-period",
        "range": "-100 to +100",
        "dtype": "numeric",
        "description": "Aroon_Up minus Aroon_Down. Positive = bullish trend inception, negative = bearish.",
    },

    # ── Momentum ───────────────────────────────────────────────────────────
    "RSI": {
        "name": "Relative Strength Index",
        "category": "Momentum",
        "parameters": "14-period",
        "range": "0-100",
        "dtype": "numeric",
        "description": "Measures speed/magnitude of price changes. >70 = overbought, <30 = oversold.",
    },
    "Stoch_RSI_K": {
        "name": "Stochastic RSI %K",
        "category": "Momentum",
        "parameters": "length=14, K=3, D=3",
        "range": "0-1",
        "dtype": "numeric",
        "description": "Stochastic oscillator applied to RSI. More sensitive than raw RSI. Normalized to [0,1].",
    },
    "Stoch_RSI_D": {
        "name": "Stochastic RSI %D",
        "category": "Momentum",
        "parameters": "length=14, K=3, D=3",
        "range": "0-1",
        "dtype": "numeric",
        "description": "Signal line (3-period SMA of %K). K crossing above D = bullish, below = bearish.",
    },
    "Stoch_K": {
        "name": "Stochastic %K",
        "category": "Momentum",
        "parameters": "K=14, D=3",
        "range": "0-100",
        "dtype": "numeric",
        "description": "Raw price stochastic — where close sits within the high-low range. Separate from StochRSI.",
    },
    "Stoch_D": {
        "name": "Stochastic %D",
        "category": "Momentum",
        "parameters": "K=14, D=3",
        "range": "0-100",
        "dtype": "numeric",
        "description": "Signal line for Stochastic. Crossovers generate buy/sell signals.",
    },
    "MACD_Line": {
        "name": "MACD",
        "category": "Momentum",
        "parameters": "fast=12, slow=26",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "Difference between 12-period and 26-period EMA. Positive = bullish momentum.",
    },
    "MACD_Signal": {
        "name": "MACD Signal Line",
        "category": "Momentum",
        "parameters": "signal=9",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "9-period EMA of MACD Line. MACD crossing above Signal = bullish crossover.",
    },
    "MACD_Histogram": {
        "name": "MACD Histogram",
        "category": "Momentum",
        "parameters": "-",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "MACD Line minus Signal Line. Measures momentum acceleration/deceleration.",
    },
    "Williams_R_14": {
        "name": "Williams %R",
        "category": "Momentum",
        "parameters": "14-period",
        "range": "-100 to 0",
        "dtype": "numeric",
        "description": "Where close sits relative to the 14-period high-low range. >-20 = overbought, <-80 = oversold.",
    },
    "CCI_20": {
        "name": "Commodity Channel Index",
        "category": "Momentum",
        "parameters": "20-period",
        "range": "Unbounded (typically -200 to +200)",
        "dtype": "numeric",
        "description": "Measures price deviation from its statistical mean. >+100 = overbought, <-100 = oversold.",
    },
    "TRIX_18": {
        "name": "TRIX",
        "category": "Momentum",
        "parameters": "18-period",
        "range": "Unbounded (small)",
        "dtype": "numeric",
        "description": "Rate-of-change of triple-smoothed EMA. Filters out insignificant price moves; cleaner than ROC.",
    },

    # ── Volume ─────────────────────────────────────────────────────────────
    "OBV": {
        "name": "On-Balance Volume",
        "category": "Volume",
        "parameters": "-",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "Running total: adds volume on up-closes, subtracts on down-closes. Confirms/diverges price trend.",
    },
    "CMF_20": {
        "name": "Chaikin Money Flow",
        "category": "Volume",
        "parameters": "20-period",
        "range": "-1 to +1",
        "dtype": "numeric",
        "description": "Measures buying vs selling pressure using close position within the high-low range, weighted by volume.",
    },
    "MFI_14": {
        "name": "Money Flow Index",
        "category": "Volume",
        "parameters": "14-period",
        "range": "0-100",
        "dtype": "numeric",
        "description": "Volume-weighted RSI — combines price and volume for overbought/oversold signals. >80 = overbought, <20 = oversold.",
    },

    # ── Volatility ─────────────────────────────────────────────────────────
    "BB_High": {
        "name": "Bollinger Band Upper",
        "category": "Volatility",
        "parameters": "20-period, 2 std",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Upper band: SMA(20) + 2 standard deviations. Price touching = potentially overbought.",
    },
    "BB_Low": {
        "name": "Bollinger Band Lower",
        "category": "Volatility",
        "parameters": "20-period, 2 std",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Lower band: SMA(20) - 2 standard deviations. Price touching = potentially oversold.",
    },
    "Donchian_High": {
        "name": "Donchian Channel Upper",
        "category": "Volatility",
        "parameters": "20-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Highest high over the last 20 bars. Breakout above = bullish signal.",
    },
    "Donchian_Low": {
        "name": "Donchian Channel Lower",
        "category": "Volatility",
        "parameters": "20-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Lowest low over the last 20 bars. Breakout below = bearish signal.",
    },
    "Donchian_Mid": {
        "name": "Donchian Channel Midline",
        "category": "Volatility",
        "parameters": "20-period",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Midpoint of upper and lower Donchian bands. Dynamic support/resistance.",
    },
    "ATR_14": {
        "name": "Average True Range",
        "category": "Volatility",
        "parameters": "14-period",
        "range": "Price scale (absolute)",
        "dtype": "numeric",
        "description": "Measures average volatility in price units. Used for position sizing and stop placement.",
    },
    "NATR_14": {
        "name": "Normalized ATR",
        "category": "Volatility",
        "parameters": "14-period",
        "range": "0-100 (percentage)",
        "dtype": "numeric",
        "description": "ATR as a percentage of close price. Enables volatility comparison across tokens and timeframes.",
    },
    "Parkinson_Vol_14": {
        "name": "Parkinson Volatility",
        "category": "Volatility",
        "parameters": "14-period",
        "range": "0+",
        "dtype": "numeric",
        "description": "Volatility estimator using high-low range (more efficient than close-to-close).",
    },
    "Realized_Vol_14": {
        "name": "Realized Volatility",
        "category": "Volatility",
        "parameters": "14-period",
        "range": "0+",
        "dtype": "numeric",
        "description": "Annualized standard deviation of log returns over 14 bars.",
    },
    "Realized_Vol_30": {
        "name": "Realized Volatility",
        "category": "Volatility",
        "parameters": "30-period",
        "range": "0+",
        "dtype": "numeric",
        "description": "Annualized standard deviation of log returns over 30 bars. Smoother, longer-term view.",
    },
    "Vol_Ratio_14_30": {
        "name": "Volatility Ratio",
        "category": "Volatility",
        "parameters": "14/30",
        "range": "0+",
        "dtype": "numeric",
        "description": "Short-term vol divided by long-term vol. >1 = volatility expanding, <1 = contracting. Regime signal.",
    },
    "CHOP_14": {
        "name": "Choppiness Index",
        "category": "Volatility",
        "parameters": "14-period",
        "range": "0-100",
        "dtype": "numeric",
        "description": "Classifies market regime. >61.8 = choppy/ranging, <38.2 = trending. Based on ATR vs Donchian range.",
    },
    "Squeeze_Flag": {
        "name": "Squeeze Indicator",
        "category": "Volatility",
        "parameters": "default",
        "range": "0 or 1",
        "dtype": "numeric",
        "description": "1 = Bollinger Bands inside Keltner Channels (squeeze is on). Precedes explosive moves.",
    },
    "Squeeze_Momentum": {
        "name": "Squeeze Momentum Value",
        "category": "Volatility",
        "parameters": "default",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "Momentum magnitude during/after a squeeze. Positive = bullish momentum, negative = bearish.",
    },

    # ── Risk ────────────────────────────────────────────────────────────────
    "VaR_5_50": {
        "name": "Value at Risk (5th percentile)",
        "category": "Risk",
        "parameters": "50-period, 5th percentile",
        "range": "Unbounded (negative)",
        "dtype": "numeric",
        "description": "5th percentile of rolling 50-period log returns. Estimates worst expected single-bar loss at 95% confidence.",
    },
    "CVaR_5_50": {
        "name": "Conditional VaR (Expected Shortfall)",
        "category": "Risk",
        "parameters": "50-period, 5th percentile",
        "range": "Unbounded (negative)",
        "dtype": "numeric",
        "description": "Mean of log returns below the 5th percentile. Measures average loss in the worst 5% of outcomes — always <= VaR.",
    },
    "Omega_Ratio_50": {
        "name": "Omega Ratio",
        "category": "Risk",
        "parameters": "50-period, threshold=0",
        "range": "0+",
        "dtype": "numeric",
        "description": "Sum of positive returns / abs(sum of negative returns) over 50 bars. >1 = gains outweigh losses. Risk-reward quality metric.",
    },
    "Tail_Ratio_50": {
        "name": "Tail Ratio",
        "category": "Risk",
        "parameters": "50-period",
        "range": "0+",
        "dtype": "numeric",
        "description": "95th percentile / abs(5th percentile) of rolling 50-period returns. >1 = right tail fatter (positive skew), <1 = left tail fatter.",
    },
    "Ulcer_Index_14": {
        "name": "Ulcer Index",
        "category": "Risk",
        "parameters": "14-period",
        "range": "0+",
        "dtype": "numeric",
        "description": "RMS of percentage drawdowns from rolling 14-period high. Higher = deeper/longer drawdowns. Pure downside risk measure.",
    },
    "Kappa_Ratio_50": {
        "name": "Kappa Ratio (order 3)",
        "category": "Risk",
        "parameters": "50-period, order=3",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "Mean return / cube-root of lower partial moment (order 3). Reward-to-downside-risk ratio that penalizes large losses cubically.",
    },

    # ── Price Levels ───────────────────────────────────────────────────────
    "VWAP": {
        "name": "Volume Weighted Average Price",
        "category": "Price Levels",
        "parameters": "Rolling 24-bar (intraday) / cumulative (daily)",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Average price weighted by volume. Institutional benchmark — price above VWAP = bullish intraday bias.",
    },
    "Fib_236": {
        "name": "Fibonacci 23.6% Retracement",
        "category": "Price Levels",
        "parameters": "50-period rolling",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Shallowest Fibonacci level. Strong trend pullbacks often find support here.",
    },
    "Fib_382": {
        "name": "Fibonacci 38.2% Retracement",
        "category": "Price Levels",
        "parameters": "50-period rolling",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Common retracement in trending markets. Often the first meaningful support/resistance.",
    },
    "Fib_500": {
        "name": "Fibonacci 50% Retracement",
        "category": "Price Levels",
        "parameters": "50-period rolling",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Psychological midpoint of the range. Not a true Fibonacci number but widely watched.",
    },
    "Fib_618": {
        "name": "Fibonacci 61.8% Retracement",
        "category": "Price Levels",
        "parameters": "50-period rolling",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "The golden ratio level. Deep retracement; often the last defense before trend reversal.",
    },
    "Fib_100": {
        "name": "Fibonacci 100% (Range Low)",
        "category": "Price Levels",
        "parameters": "50-period rolling",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Bottom of the 50-period range. Full retracement level.",
    },

    # ── Custom ─────────────────────────────────────────────────────────────
    "HDPR_MA": {
        "name": "HDPR Moving Average",
        "category": "Custom",
        "parameters": "50-period (reuses SMA_50)",
        "range": "Price scale",
        "dtype": "numeric",
        "description": "Mean-reversion reference line. Equal to SMA_50.",
    },
    "HDPR_Distance": {
        "name": "HDPR Distance",
        "category": "Custom",
        "parameters": "-",
        "range": "Unbounded (fraction)",
        "dtype": "numeric",
        "description": "(Close - SMA_50) / SMA_50. Measures percentage deviation from the 50-period mean.",
    },
    "HDPR_Signal": {
        "name": "HDPR Signal",
        "category": "Custom",
        "parameters": "threshold=3%",
        "range": "-1, 0, or +1",
        "dtype": "numeric",
        "description": "Mean-reversion signal: +1 = price >3% below MA (buy), -1 = price >3% above MA (sell), 0 = neutral.",
    },

    # ── Log Returns ────────────────────────────────────────────────────────
    "LogReturn_1": {
        "name": "1-period Log Return",
        "category": "Log Returns",
        "parameters": "-",
        "range": "Unbounded (small)",
        "dtype": "numeric",
        "description": "ln(Close / Close[-1]). Single-bar return. Approximately symmetric and additive.",
    },
    "LogReturn_4": {
        "name": "4-period Log Return",
        "category": "Log Returns",
        "parameters": "-",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "Return over 4 bars. For 1h data = 4-hour return.",
    },
    "LogReturn_12": {
        "name": "12-period Log Return",
        "category": "Log Returns",
        "parameters": "-",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "Return over 12 bars. For 1h data = 12-hour return.",
    },
    "LogReturn_24": {
        "name": "24-period Log Return",
        "category": "Log Returns",
        "parameters": "-",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "Return over 24 bars. For 1h data = daily return.",
    },

    # ── Temporal ───────────────────────────────────────────────────────────
    "Hour_Sin": {
        "name": "Hour of Day (sine)",
        "category": "Temporal",
        "parameters": "-",
        "range": "-1 to +1",
        "dtype": "numeric",
        "description": "Cyclical encoding of hour: sin(2pi * hour / 24). Captures time-of-day seasonality for ML.",
    },
    "Hour_Cos": {
        "name": "Hour of Day (cosine)",
        "category": "Temporal",
        "parameters": "-",
        "range": "-1 to +1",
        "dtype": "numeric",
        "description": "Cyclical encoding of hour: cos(2pi * hour / 24). Paired with sine for full representation.",
    },
    "DOW_Sin": {
        "name": "Day of Week (sine)",
        "category": "Temporal",
        "parameters": "-",
        "range": "-1 to +1",
        "dtype": "numeric",
        "description": "Cyclical encoding of weekday: sin(2pi * dow / 7). Captures weekly seasonality.",
    },
    "DOW_Cos": {
        "name": "Day of Week (cosine)",
        "category": "Temporal",
        "parameters": "-",
        "range": "-1 to +1",
        "dtype": "numeric",
        "description": "Cyclical encoding of weekday: cos(2pi * dow / 7).",
    },

    # ── ML Features ────────────────────────────────────────────────────────
    "Close_ZScore_100": {
        "name": "Close Price Z-Score",
        "category": "ML Features",
        "parameters": "100-period",
        "range": "Unbounded (typically -3 to +3)",
        "dtype": "numeric",
        "description": "(Close - rolling_mean) / rolling_std. Makes price stationary. >+2 = unusually high, <-2 = unusually low.",
    },
    "RSI_ZScore_100": {
        "name": "RSI Z-Score",
        "category": "ML Features",
        "parameters": "100-period",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "Standardizes RSI relative to its own recent history. Detects when RSI itself is at extremes.",
    },
    "Volume_ZScore_100": {
        "name": "Volume Z-Score",
        "category": "ML Features",
        "parameters": "100-period",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "Detects anomalous volume spikes. >+2 = unusually high volume event.",
    },
    "Candle_Body_Ratio": {
        "name": "Candle Body Size",
        "category": "ML Features",
        "parameters": "ATR-normalized",
        "range": "0+",
        "dtype": "numeric",
        "description": "abs(Close - Open) / ATR_14. Large body = strong conviction; small body = indecision.",
    },
    "Upper_Wick_Ratio": {
        "name": "Upper Wick Size",
        "category": "ML Features",
        "parameters": "ATR-normalized",
        "range": "0+",
        "dtype": "numeric",
        "description": "(High - max(Open,Close)) / ATR_14. Large upper wick = selling rejection from above.",
    },
    "Lower_Wick_Ratio": {
        "name": "Lower Wick Size",
        "category": "ML Features",
        "parameters": "ATR-normalized",
        "range": "0+",
        "dtype": "numeric",
        "description": "(min(Open,Close) - Low) / ATR_14. Large lower wick = buying rejection from below.",
    },
    "Price_vs_EMA20": {
        "name": "Price Distance from EMA 20",
        "category": "ML Features",
        "parameters": "ATR-normalized",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "(Close - EMA_20) / ATR_14. Positive = above EMA, negative = below. Continuous HDPR alternative.",
    },
    "Price_vs_SMA200": {
        "name": "Price Distance from SMA 200",
        "category": "ML Features",
        "parameters": "ATR-normalized",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "(Close - SMA_200) / ATR_14. Macro trend positioning — how extended price is from long-term average.",
    },
    "BB_Width": {
        "name": "Bollinger Band Width",
        "category": "ML Features",
        "parameters": "-",
        "range": "0+",
        "dtype": "numeric",
        "description": "(BB_High - BB_Low) / Close. Squeeze proxy: low width = compression, high = expansion.",
    },
    "RSI_Slope_3": {
        "name": "RSI 3-bar Slope",
        "category": "ML Features",
        "parameters": "-",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "RSI.diff(3). Positive = RSI accelerating upward, negative = decelerating. Momentum direction.",
    },
    "MACD_Slope_3": {
        "name": "MACD Histogram 3-bar Slope",
        "category": "ML Features",
        "parameters": "-",
        "range": "Unbounded",
        "dtype": "numeric",
        "description": "MACD_Histogram.diff(3). Positive = momentum strengthening, negative = weakening.",
    },

    # ── Sentiment ──────────────────────────────────────────────────────────
    "FnG_Value": {
        "name": "Fear & Greed Index",
        "category": "Sentiment",
        "parameters": "-",
        "range": "0-100",
        "dtype": "numeric",
        "description": "Crypto Fear & Greed Index. 0 = Extreme Fear, 100 = Extreme Greed. Daily resolution.",
    },
    "FnG_Class": {
        "name": "Fear & Greed Classification",
        "category": "Sentiment",
        "parameters": "-",
        "range": "5 categories",
        "dtype": "string",
        "description": "Classification: Extreme Fear, Fear, Neutral, Greed, Extreme Greed. null if API unreachable.",
    },
}


def get_glossary_document() -> dict:
    """Build the MongoDB metadata document from INDICATOR_GLOSSARY.

    Returns a dict ready for upsert into the indicator_metadata collection.
    The schema_hash (SHA-256 of sorted column names) lets downstream consumers
    cheaply detect schema changes without diffing the full document.
    """
    numeric_cols = sorted(
        k for k, v in INDICATOR_GLOSSARY.items() if v["dtype"] == "numeric"
    )
    string_cols = sorted(
        k for k, v in INDICATOR_GLOSSARY.items() if v["dtype"] == "string"
    )
    all_cols = sorted(INDICATOR_GLOSSARY.keys())

    schema_hash = hashlib.sha256(
        json.dumps(all_cols, sort_keys=True).encode()
    ).hexdigest()

    # Build category summary with deterministic ordering
    cat_map: dict[str, list[str]] = {}
    for col, meta in INDICATOR_GLOSSARY.items():
        cat_map.setdefault(meta["category"], []).append(col)

    categories = []
    for cat in CATEGORY_ORDER:
        if cat in cat_map:
            categories.append({
                "name": cat,
                "columns": sorted(cat_map[cat]),
                "count": len(cat_map[cat]),
            })

    return {
        "_id": "indicator_glossary",
        "version": 1,
        "schema_hash": schema_hash,
        "updated_at": datetime.now(timezone.utc),
        "total_numeric": len(numeric_cols),
        "total_string": len(string_cols),
        "total_columns": len(all_cols),
        "base_columns": ["Open", "High", "Low", "Close", "Volume", "timestamp"],
        "categories": categories,
        "indicators": dict(INDICATOR_GLOSSARY),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_all(df: pd.DataFrame, timeframe: str = "1h") -> pd.DataFrame:
    """Compute every indicator on the OHLCV DataFrame (in-place + return).

    The DataFrame index must be a DatetimeIndex (UTC).
    Requires columns: Open, High, Low, Close, Volume.

    Parameters:
        df: OHLCV DataFrame
        timeframe: "1h", "4h", or "1d" — affects VWAP calculation
    """
    _compute_moving_averages(df)
    _compute_momentum(df)
    _compute_volatility_bands(df)
    _compute_ichimoku(df)
    _compute_macd(df)
    _compute_donchian(df)
    _compute_atr(df)
    _compute_adx(df)
    _compute_vwap(df, timeframe)
    _compute_williams_r(df)
    _compute_cci(df)
    _compute_log_returns(df)
    _compute_parkinson_volatility(df)
    _compute_realized_volatility(df)
    _compute_volatility_ratio(df)
    _compute_risk_metrics(df)
    _compute_fibonacci(df)
    _compute_hdpr(df)
    _compute_temporal_features(df)
    # --- New Tier 1 indicators ---
    _compute_obv(df)
    _compute_cmf(df)
    _compute_mfi(df)
    _compute_supertrend(df)
    _compute_natr(df)
    _compute_kama(df)
    _compute_chop(df)
    # --- New Tier 2 indicators ---
    _compute_squeeze(df)
    _compute_aroon(df)
    _compute_hma(df)
    _compute_psar(df)
    _compute_stoch(df)
    _compute_trix(df)
    # --- ML feature engineering ---
    _compute_ml_features(df)
    return df


def get_numeric_cols() -> list[str]:
    """Column names used for NaN validation (all numeric indicator columns).

    Derived from INDICATOR_GLOSSARY — excludes FnG_Value because it is
    nullable (filled per-pipeline-run, not per-row) and should not cause
    a row to be dropped during NaN validation.
    """
    _EXCLUDE = {"FnG_Value"}
    return [
        col for col, meta in INDICATOR_GLOSSARY.items()
        if meta["dtype"] == "numeric" and col not in _EXCLUDE
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
# Momentum (RSI + Stochastic RSI)
# ---------------------------------------------------------------------------

def _compute_momentum(df: pd.DataFrame):
    df["RSI"] = ta.rsi(df["Close"], length=14)

    stoch_rsi = ta.stochrsi(df["Close"], length=14, rsi_length=14, k=3, d=3)
    if stoch_rsi is not None and not stoch_rsi.empty:
        cols = stoch_rsi.columns.tolist()
        # pandas_ta returns [0,100]; normalize to [0,1] for compatibility
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

def _compute_vwap(df: pd.DataFrame, timeframe: str = "1h"):
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    if timeframe == "1d":
        # Cumulative VWAP for daily — no session reset needed
        df["VWAP"] = (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()
    else:
        # Rolling 24-bar VWAP for intraday (1h=24h session, 4h=4-day window)
        window = 24
        df["VWAP"] = (
            (tp * df["Volume"]).rolling(window).sum()
            / df["Volume"].rolling(window).sum()
        )


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
# Risk Metrics (VaR, CVaR, Omega, Tail Ratio, Ulcer Index, Kappa)
# ---------------------------------------------------------------------------

def _compute_risk_metrics(df: pd.DataFrame):
    """Rolling risk/tail metrics derived from LogReturn_1 and Close."""
    if "LogReturn_1" not in df.columns:
        return

    ret = df["LogReturn_1"]
    window = 50

    # --- VaR (5th percentile of returns) ---
    df["VaR_5_50"] = ret.rolling(window).quantile(0.05)

    # --- CVaR (Expected Shortfall) ---
    def _cvar(x):
        threshold = np.quantile(x, 0.05)
        tail = x[x <= threshold]
        return tail.mean() if len(tail) > 0 else threshold

    df["CVaR_5_50"] = ret.rolling(window).apply(_cvar, raw=True)

    # --- Omega Ratio ---
    pos_sum = ret.clip(lower=0).rolling(window).sum()
    neg_sum = ret.clip(upper=0).rolling(window).sum()
    df["Omega_Ratio_50"] = pos_sum / neg_sum.abs()
    # All positive returns -> neg_sum=0 -> inf; replace with NaN
    df.loc[neg_sum == 0, "Omega_Ratio_50"] = np.nan

    # --- Tail Ratio ---
    q95 = ret.rolling(window).quantile(0.95)
    q05 = ret.rolling(window).quantile(0.05)
    df["Tail_Ratio_50"] = q95 / q05.abs()
    # 5th percentile=0 -> division by zero; replace with NaN
    df.loc[q05 == 0, "Tail_Ratio_50"] = np.nan

    # --- Ulcer Index (14-period, based on Close prices) ---
    ui_window = 14
    rolling_max = df["Close"].rolling(ui_window).max()
    drawdown_pct = (df["Close"] - rolling_max) / rolling_max * 100
    df["Ulcer_Index_14"] = np.sqrt((drawdown_pct ** 2).rolling(ui_window).mean())

    # --- Kappa Ratio (order 3) ---
    mean_ret = ret.rolling(window).mean()

    def _lpm3(x):
        losses = np.minimum(x, 0)
        return np.mean(losses ** 3)

    lpm3 = ret.rolling(window).apply(_lpm3, raw=True)
    # Cube root of negative LPM3 (losses cubed are negative)
    safe_lpm3 = lpm3.replace(0, np.nan)
    df["Kappa_Ratio_50"] = mean_ret / np.cbrt(safe_lpm3.abs())
    # Sign: LPM3 of losses is negative, abs + cbrt makes denominator positive
    # If all returns positive, LPM3=0 -> NaN (correct)


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
    # Reuse SMA_50 instead of recomputing
    df["HDPR_MA"]       = df["SMA_50"]
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


# ===========================================================================
# Tier 1 — New Indicators
# ===========================================================================

# ---------------------------------------------------------------------------
# OBV (On-Balance Volume)
# ---------------------------------------------------------------------------

def _compute_obv(df: pd.DataFrame):
    result = ta.obv(df["Close"], df["Volume"])
    if result is not None:
        df["OBV"] = result


# ---------------------------------------------------------------------------
# CMF (Chaikin Money Flow, 20)
# ---------------------------------------------------------------------------

def _compute_cmf(df: pd.DataFrame):
    result = ta.cmf(df["High"], df["Low"], df["Close"], df["Volume"], length=20)
    if result is not None:
        df["CMF_20"] = result


# ---------------------------------------------------------------------------
# MFI (Money Flow Index, 14)
# ---------------------------------------------------------------------------

def _compute_mfi(df: pd.DataFrame):
    result = ta.mfi(df["High"], df["Low"], df["Close"], df["Volume"], length=14)
    if result is not None:
        df["MFI_14"] = result


# ---------------------------------------------------------------------------
# Supertrend (7, 3.0)
# ---------------------------------------------------------------------------

def _compute_supertrend(df: pd.DataFrame):
    result = ta.supertrend(df["High"], df["Low"], df["Close"],
                           length=7, multiplier=3.0)
    if result is not None and not result.empty:
        cols = result.columns.tolist()
        # Returns: SUPERT_7_3.0, SUPERTd_7_3.0, SUPERTl_7_3.0, SUPERTs_7_3.0
        for col in cols:
            if col.startswith("SUPERTd"):
                df["Supertrend_Direction"] = result[col]
            elif col.startswith("SUPERT_") or col.startswith("SUPERTl") or col.startswith("SUPERTs"):
                # Use the main SUPERT value (trend line)
                if col.startswith("SUPERT_"):
                    df["Supertrend_Value"] = result[col]


# ---------------------------------------------------------------------------
# NATR (Normalized ATR, 14)
# ---------------------------------------------------------------------------

def _compute_natr(df: pd.DataFrame):
    result = ta.natr(df["High"], df["Low"], df["Close"], length=14)
    if result is not None:
        df["NATR_14"] = result


# ---------------------------------------------------------------------------
# KAMA (Kaufman Adaptive MA, 10)
# ---------------------------------------------------------------------------

def _compute_kama(df: pd.DataFrame):
    result = ta.kama(df["Close"], length=10)
    if result is not None:
        df["KAMA_10"] = result


# ---------------------------------------------------------------------------
# Choppiness Index (14)
# ---------------------------------------------------------------------------

def _compute_chop(df: pd.DataFrame):
    result = ta.chop(df["High"], df["Low"], df["Close"], length=14)
    if result is not None:
        df["CHOP_14"] = result


# ===========================================================================
# Tier 2 — New Indicators
# ===========================================================================

# ---------------------------------------------------------------------------
# Squeeze Momentum (BB inside KC)
# ---------------------------------------------------------------------------

def _compute_squeeze(df: pd.DataFrame):
    result = ta.squeeze(df["High"], df["Low"], df["Close"])
    if result is not None and not result.empty:
        cols = result.columns.tolist()
        for col in cols:
            if col.startswith("SQZ_ON"):
                df["Squeeze_Flag"] = result[col]
            elif col.startswith("SQZ_") and "ON" not in col and "OFF" not in col and "NO" not in col:
                df["Squeeze_Momentum"] = result[col]


# ---------------------------------------------------------------------------
# Aroon Oscillator (25)
# ---------------------------------------------------------------------------

def _compute_aroon(df: pd.DataFrame):
    result = ta.aroon(df["High"], df["Low"], length=25)
    if result is not None and not result.empty:
        cols = result.columns.tolist()
        for col in cols:
            if col.startswith("AROOND"):
                df["Aroon_Down"] = result[col]
            elif col.startswith("AROONU"):
                df["Aroon_Up"] = result[col]
            elif col.startswith("AROONOSC"):
                df["Aroon_Osc"] = result[col]


# ---------------------------------------------------------------------------
# HMA (Hull Moving Average, 20)
# ---------------------------------------------------------------------------

def _compute_hma(df: pd.DataFrame):
    result = ta.hma(df["Close"], length=20)
    if result is not None:
        df["HMA_20"] = result


# ---------------------------------------------------------------------------
# PSAR (Parabolic SAR)
# ---------------------------------------------------------------------------

def _compute_psar(df: pd.DataFrame):
    result = ta.psar(df["High"], df["Low"])
    if result is not None and not result.empty:
        cols = result.columns.tolist()
        # PSAR returns: PSARl, PSARs, PSARaf, PSARr
        # Combine long and short into a single PSAR value
        psar_long = None
        psar_short = None
        for col in cols:
            if col.startswith("PSARl"):
                psar_long = result[col]
            elif col.startswith("PSARs"):
                psar_short = result[col]
        if psar_long is not None and psar_short is not None:
            df["PSAR"] = psar_long.fillna(psar_short)
        elif psar_long is not None:
            df["PSAR"] = psar_long
        elif psar_short is not None:
            df["PSAR"] = psar_short


# ---------------------------------------------------------------------------
# Stochastic (K=14, D=3) — raw price stochastic, separate from StochRSI
# ---------------------------------------------------------------------------

def _compute_stoch(df: pd.DataFrame):
    result = ta.stoch(df["High"], df["Low"], df["Close"], k=14, d=3)
    if result is not None and not result.empty:
        cols = result.columns.tolist()
        for col in cols:
            if col.startswith("STOCHk"):
                df["Stoch_K"] = result[col]
            elif col.startswith("STOCHd"):
                df["Stoch_D"] = result[col]


# ---------------------------------------------------------------------------
# TRIX (18)
# ---------------------------------------------------------------------------

def _compute_trix(df: pd.DataFrame):
    result = ta.trix(df["Close"], length=18)
    if result is not None and not result.empty:
        cols = result.columns.tolist()
        # Returns: TRIX_18_9, TRIXs_18_9
        for col in cols:
            if col.startswith("TRIX_"):
                df["TRIX_18"] = result[col]
                break


# ===========================================================================
# ML Feature Engineering
# ===========================================================================

def _compute_ml_features(df: pd.DataFrame):
    """Derived features for ML models — computed from existing indicators."""

    # Z-scores (100-period)
    _z = lambda s: (s - s.rolling(100).mean()) / s.rolling(100).std()

    df["Close_ZScore_100"]  = _z(df["Close"])
    df["RSI_ZScore_100"]    = _z(df["RSI"]) if "RSI" in df.columns else np.nan
    df["Volume_ZScore_100"] = _z(df["Volume"])

    # Candle body and wick ratios (ATR-normalized)
    atr = df.get("ATR_14")
    if atr is not None:
        safe_atr = atr.replace(0, np.nan)
        df["Candle_Body_Ratio"] = abs(df["Close"] - df["Open"]) / safe_atr
        df["Upper_Wick_Ratio"]  = (
            (df["High"] - df[["Open", "Close"]].max(axis=1)) / safe_atr
        )
        df["Lower_Wick_Ratio"]  = (
            (df[["Open", "Close"]].min(axis=1) - df["Low"]) / safe_atr
        )
    else:
        df["Candle_Body_Ratio"] = np.nan
        df["Upper_Wick_Ratio"]  = np.nan
        df["Lower_Wick_Ratio"]  = np.nan

    # Price distance from key MAs (ATR-normalized)
    if atr is not None:
        safe_atr = atr.replace(0, np.nan)
        df["Price_vs_EMA20"]  = (df["Close"] - df.get("EMA_20", np.nan)) / safe_atr
        df["Price_vs_SMA200"] = (df["Close"] - df.get("SMA_200", np.nan)) / safe_atr
    else:
        df["Price_vs_EMA20"]  = np.nan
        df["Price_vs_SMA200"] = np.nan

    # BB Width
    if "BB_High" in df.columns and "BB_Low" in df.columns:
        df["BB_Width"] = (df["BB_High"] - df["BB_Low"]) / df["Close"]
    else:
        df["BB_Width"] = np.nan

    # Momentum slopes
    if "RSI" in df.columns:
        df["RSI_Slope_3"] = df["RSI"].diff(3)
    else:
        df["RSI_Slope_3"] = np.nan

    if "MACD_Histogram" in df.columns:
        df["MACD_Slope_3"] = df["MACD_Histogram"].diff(3)
    else:
        df["MACD_Slope_3"] = np.nan
