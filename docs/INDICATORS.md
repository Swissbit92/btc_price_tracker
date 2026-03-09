# Indicator Glossary

> **Single source of truth:** `btc_tracker_mongodb/indicators.py`
> If you add, remove, or rename any indicator column, update the `INDICATOR_GLOSSARY` dict in `indicators.py` — `get_numeric_cols()` derives from it automatically. Also update **this file** and the indicator summary in `CLAUDE.md`.

> **Programmatic access:** The glossary is also stored in MongoDB as a self-describing document. Query it from any consumer:
> ```python
> db.indicator_metadata.find_one({"_id": "indicator_glossary"})
> ```
> The document includes column names, descriptions, categories, ranges, and a `schema_hash` for change detection. It is automatically synced on every pipeline run (seed or update).

Each document stored in MongoDB contains OHLCV fields (`Open`, `High`, `Low`, `Close`, `Volume`, `timestamp`) plus the indicator columns listed below.

---

## Trend Indicators

| Column | Indicator | Parameters | Range | Description |
|---|---|---|---|---|
| `SMA_50` | Simple Moving Average | 50-period | Price scale | Average closing price over the last 50 bars. Smooths noise; acts as dynamic support/resistance. |
| `SMA_100` | Simple Moving Average | 100-period | Price scale | Medium-term trend filter. Price above = bullish bias. |
| `SMA_200` | Simple Moving Average | 200-period | Price scale | Long-term trend benchmark. The "bull/bear market" dividing line. |
| `EMA_20` | Exponential Moving Average | 20-period | Price scale | Fast trend tracker. Weights recent prices more than SMA. |
| `EMA_50` | Exponential Moving Average | 50-period | Price scale | Medium trend. Crossovers with EMA_20 signal momentum shifts. |
| `EMA_100` | Exponential Moving Average | 100-period | Price scale | Intermediate trend filter between 50 and 200. |
| `EMA_200` | Exponential Moving Average | 200-period | Price scale | Long-term EMA. More responsive than SMA_200 to recent data. |
| `Ichimoku_Conversion` | Ichimoku Tenkan-sen | 9-period | Price scale | Short-term midpoint: (9-period high + 9-period low) / 2. Signals short-term momentum. |
| `Ichimoku_Base` | Ichimoku Kijun-sen | 26-period | Price scale | Medium-term midpoint. Acts as support/resistance; flat = ranging market. |
| `Ichimoku_A` | Ichimoku Senkou Span A | (9+26)/2 | Price scale | Leading span A of the cloud. Midpoint of Conversion and Base, projected forward. |
| `Ichimoku_B` | Ichimoku Senkou Span B | 52-period | Price scale | Leading span B. Slowest cloud component; defines cloud thickness. |
| `ADX_14` | Average Directional Index | 14-period | 0–100 | Measures trend **strength** (not direction). < 20 = weak/no trend, > 25 = trending, > 50 = strong trend. |
| `DI_Plus_14` | Positive Directional Indicator | 14-period | 0–100 | Measures upward movement strength. DI+ > DI- suggests bullish pressure. |
| `DI_Minus_14` | Negative Directional Indicator | 14-period | 0–100 | Measures downward movement strength. DI- > DI+ suggests bearish pressure. |
| `Supertrend_Value` | Supertrend Line | length=7, mult=3.0 | Price scale | ATR-based trailing stop line. Price above = uptrend, below = downtrend. |
| `Supertrend_Direction` | Supertrend Direction | length=7, mult=3.0 | -1 or +1 | Binary trend signal: +1 = uptrend, -1 = downtrend. Directly actionable. |
| `KAMA_10` | Kaufman Adaptive Moving Average | 10-period | Price scale | Adapts speed to volatility: fast in trends, flat in chop. Superior noise filtering vs SMA/EMA. |
| `HMA_20` | Hull Moving Average | 20-period | Price scale | Dramatically reduced lag while remaining smooth. Uses weighted MA of WMAs. |
| `PSAR` | Parabolic SAR | default af/max | Price scale | Trend-following trailing stop. Dots flip above/below price on trend reversal. |
| `Aroon_Up` | Aroon Up | 25-period | 0–100 | Measures bars since highest high. 100 = new high just made, 0 = no new high in 25 bars. |
| `Aroon_Down` | Aroon Down | 25-period | 0–100 | Measures bars since lowest low. 100 = new low just made. |
| `Aroon_Osc` | Aroon Oscillator | 25-period | -100 to +100 | Aroon_Up minus Aroon_Down. Positive = bullish trend inception, negative = bearish. |

---

## Momentum Indicators

| Column | Indicator | Parameters | Range | Description |
|---|---|---|---|---|
| `RSI` | Relative Strength Index | 14-period | 0–100 | Measures speed/magnitude of price changes. > 70 = overbought, < 30 = oversold. |
| `Stoch_RSI_K` | Stochastic RSI %K | length=14, K=3, D=3 | 0–1 | Stochastic oscillator applied to RSI. More sensitive than raw RSI. Normalized to [0,1]. |
| `Stoch_RSI_D` | Stochastic RSI %D | length=14, K=3, D=3 | 0–1 | Signal line (3-period SMA of %K). K crossing above D = bullish, below = bearish. |
| `Stoch_K` | Stochastic %K | K=14, D=3 | 0–100 | Raw price stochastic — where close sits within the high-low range. Separate from StochRSI. |
| `Stoch_D` | Stochastic %D | K=14, D=3 | 0–100 | Signal line for Stochastic. Crossovers generate buy/sell signals. |
| `MACD_Line` | MACD | fast=12, slow=26 | Unbounded | Difference between 12-period and 26-period EMA. Positive = bullish momentum. |
| `MACD_Signal` | MACD Signal Line | signal=9 | Unbounded | 9-period EMA of MACD Line. MACD crossing above Signal = bullish crossover. |
| `MACD_Histogram` | MACD Histogram | — | Unbounded | MACD Line minus Signal Line. Measures momentum acceleration/deceleration. |
| `Williams_R_14` | Williams %R | 14-period | -100 to 0 | Where close sits relative to the 14-period high-low range. > -20 = overbought, < -80 = oversold. |
| `CCI_20` | Commodity Channel Index | 20-period | Unbounded (typically -200 to +200) | Measures price deviation from its statistical mean. > +100 = overbought, < -100 = oversold. |
| `TRIX_18` | TRIX | 18-period | Unbounded (small) | Rate-of-change of triple-smoothed EMA. Filters out insignificant price moves; cleaner than ROC. |

---

## Volume Indicators

| Column | Indicator | Parameters | Range | Description |
|---|---|---|---|---|
| `OBV` | On-Balance Volume | — | Unbounded | Running total: adds volume on up-closes, subtracts on down-closes. Confirms/diverges price trend. |
| `CMF_20` | Chaikin Money Flow | 20-period | -1 to +1 | Measures buying vs selling pressure using close position within the high-low range, weighted by volume. |
| `MFI_14` | Money Flow Index | 14-period | 0–100 | "Volume-weighted RSI" — combines price and volume for overbought/oversold signals. > 80 = overbought, < 20 = oversold. |

---

## Volatility Indicators

| Column | Indicator | Parameters | Range | Description |
|---|---|---|---|---|
| `BB_High` | Bollinger Band Upper | 20-period, 2 std | Price scale | Upper band: SMA(20) + 2 standard deviations. Price touching = potentially overbought. |
| `BB_Low` | Bollinger Band Lower | 20-period, 2 std | Price scale | Lower band: SMA(20) - 2 standard deviations. Price touching = potentially oversold. |
| `Donchian_High` | Donchian Channel Upper | 20-period | Price scale | Highest high over the last 20 bars. Breakout above = bullish signal. |
| `Donchian_Low` | Donchian Channel Lower | 20-period | Price scale | Lowest low over the last 20 bars. Breakout below = bearish signal. |
| `Donchian_Mid` | Donchian Channel Midline | 20-period | Price scale | Midpoint of upper and lower Donchian bands. Dynamic support/resistance. |
| `ATR_14` | Average True Range | 14-period | Price scale (absolute) | Measures average volatility in price units. Used for position sizing and stop placement. |
| `NATR_14` | Normalized ATR | 14-period | 0–100 (percentage) | ATR as a percentage of close price. Enables volatility comparison across tokens and timeframes. |
| `Parkinson_Vol_14` | Parkinson Volatility | 14-period | 0+ | Volatility estimator using high-low range (more efficient than close-to-close). |
| `Realized_Vol_14` | Realized Volatility | 14-period | 0+ | Annualized standard deviation of log returns over 14 bars. |
| `Realized_Vol_30` | Realized Volatility | 30-period | 0+ | Annualized standard deviation of log returns over 30 bars. Smoother, longer-term view. |
| `Vol_Ratio_14_30` | Volatility Ratio | 14/30 | 0+ | Short-term vol divided by long-term vol. > 1 = volatility expanding, < 1 = contracting. Regime signal. |
| `CHOP_14` | Choppiness Index | 14-period | 0–100 | Classifies market regime. > 61.8 = choppy/ranging, < 38.2 = trending. Based on ATR vs Donchian range. |
| `Squeeze_Flag` | Squeeze Indicator (on/off) | default | 0 or 1 | 1 = Bollinger Bands inside Keltner Channels (squeeze is on). Precedes explosive moves. |
| `Squeeze_Momentum` | Squeeze Momentum Value | default | Unbounded | Momentum magnitude during/after a squeeze. Positive = bullish momentum, negative = bearish. |

---

## Risk Indicators

| Column | Indicator | Parameters | Range | Description |
|---|---|---|---|---|
| `VaR_5_50` | Value at Risk (5th percentile) | 50-period, 5th percentile | Unbounded (negative) | 5th percentile of rolling 50-period log returns. Estimates worst expected single-bar loss at 95% confidence. |
| `CVaR_5_50` | Conditional VaR (Expected Shortfall) | 50-period, 5th percentile | Unbounded (negative) | Mean of log returns below the 5th percentile. Measures average loss in the worst 5% of outcomes — always <= VaR. |
| `Omega_Ratio_50` | Omega Ratio | 50-period, threshold=0 | 0+ | Sum of positive returns / abs(sum of negative returns) over 50 bars. >1 = gains outweigh losses. Risk-reward quality metric. |
| `Tail_Ratio_50` | Tail Ratio | 50-period | 0+ | 95th percentile / abs(5th percentile) of rolling 50-period returns. >1 = right tail fatter (positive skew), <1 = left tail fatter. |
| `Ulcer_Index_14` | Ulcer Index | 14-period | 0+ | RMS of percentage drawdowns from rolling 14-period high. Higher = deeper/longer drawdowns. Pure downside risk measure. |
| `Kappa_Ratio_50` | Kappa Ratio (order 3) | 50-period, order=3 | Unbounded | Mean return / cube-root of lower partial moment (order 3). Reward-to-downside-risk ratio that penalizes large losses cubically. |

---

## Price Level Indicators

| Column | Indicator | Parameters | Range | Description |
|---|---|---|---|---|
| `VWAP` | Volume Weighted Average Price | Rolling 24-bar (intraday) / cumulative (daily) | Price scale | Average price weighted by volume. Institutional benchmark — price above VWAP = bullish intraday bias. |
| `Fib_236` | Fibonacci 23.6% Retracement | 50-period rolling | Price scale | Shallowest Fibonacci level. Strong trend pullbacks often find support here. |
| `Fib_382` | Fibonacci 38.2% Retracement | 50-period rolling | Price scale | Common retracement in trending markets. Often the first meaningful support/resistance. |
| `Fib_500` | Fibonacci 50% Retracement | 50-period rolling | Price scale | Psychological midpoint of the range. Not a true Fibonacci number but widely watched. |
| `Fib_618` | Fibonacci 61.8% Retracement | 50-period rolling | Price scale | The "golden ratio" level. Deep retracement; often the last defense before trend reversal. |
| `Fib_100` | Fibonacci 100% (Range Low) | 50-period rolling | Price scale | Bottom of the 50-period range. Full retracement level. |

---

## Custom Indicators

| Column | Indicator | Parameters | Range | Description |
|---|---|---|---|---|
| `HDPR_MA` | HDPR Moving Average | 50-period (reuses SMA_50) | Price scale | Mean-reversion reference line. Equal to SMA_50. |
| `HDPR_Distance` | HDPR Distance | — | Unbounded (fraction) | `(Close - SMA_50) / SMA_50`. Measures percentage deviation from the 50-period mean. |
| `HDPR_Signal` | HDPR Signal | threshold=3% | -1, 0, or +1 | Mean-reversion signal: +1 = price > 3% below MA (buy), -1 = price > 3% above MA (sell), 0 = neutral. |

---

## Derived / Log Return Features

| Column | Indicator | Parameters | Range | Description |
|---|---|---|---|---|
| `LogReturn_1` | 1-period Log Return | — | Unbounded (small) | `ln(Close / Close[-1])`. Single-bar return. Approximately symmetric and additive. |
| `LogReturn_4` | 4-period Log Return | — | Unbounded | Return over 4 bars. For 1h data = 4-hour return. |
| `LogReturn_12` | 12-period Log Return | — | Unbounded | Return over 12 bars. For 1h data = 12-hour return. |
| `LogReturn_24` | 24-period Log Return | — | Unbounded | Return over 24 bars. For 1h data = daily return. |

---

## Temporal Features

| Column | Indicator | Parameters | Range | Description |
|---|---|---|---|---|
| `Hour_Sin` | Hour of Day (sine) | — | -1 to +1 | Cyclical encoding of hour: `sin(2pi * hour / 24)`. Captures time-of-day seasonality for ML. |
| `Hour_Cos` | Hour of Day (cosine) | — | -1 to +1 | Cyclical encoding of hour: `cos(2pi * hour / 24)`. Paired with sine for full representation. |
| `DOW_Sin` | Day of Week (sine) | — | -1 to +1 | Cyclical encoding of weekday: `sin(2pi * dow / 7)`. Captures weekly seasonality. |
| `DOW_Cos` | Day of Week (cosine) | — | -1 to +1 | Cyclical encoding of weekday: `cos(2pi * dow / 7)`. |

---

## ML Feature Engineering

| Column | Indicator | Parameters | Range | Description |
|---|---|---|---|---|
| `Close_ZScore_100` | Close Price Z-Score | 100-period | Unbounded (typically -3 to +3) | `(Close - rolling_mean) / rolling_std`. Makes price stationary. > +2 = unusually high, < -2 = unusually low. |
| `RSI_ZScore_100` | RSI Z-Score | 100-period | Unbounded | Standardizes RSI relative to its own recent history. Detects when RSI itself is at extremes. |
| `Volume_ZScore_100` | Volume Z-Score | 100-period | Unbounded | Detects anomalous volume spikes. > +2 = unusually high volume event. |
| `Candle_Body_Ratio` | Candle Body Size | ATR-normalized | 0+ | `abs(Close - Open) / ATR_14`. Large body = strong conviction; small body = indecision. |
| `Upper_Wick_Ratio` | Upper Wick Size | ATR-normalized | 0+ | `(High - max(Open,Close)) / ATR_14`. Large upper wick = selling rejection from above. |
| `Lower_Wick_Ratio` | Lower Wick Size | ATR-normalized | 0+ | `(min(Open,Close) - Low) / ATR_14`. Large lower wick = buying rejection from below. |
| `Price_vs_EMA20` | Price Distance from EMA 20 | ATR-normalized | Unbounded | `(Close - EMA_20) / ATR_14`. Positive = above EMA, negative = below. Continuous HDPR alternative. |
| `Price_vs_SMA200` | Price Distance from SMA 200 | ATR-normalized | Unbounded | `(Close - SMA_200) / ATR_14`. Macro trend positioning — how extended price is from long-term average. |
| `BB_Width` | Bollinger Band Width | — | 0+ | `(BB_High - BB_Low) / Close`. Squeeze proxy: low width = compression, high = expansion. |
| `RSI_Slope_3` | RSI 3-bar Slope | — | Unbounded | `RSI.diff(3)`. Positive = RSI accelerating upward, negative = decelerating. Momentum direction. |
| `MACD_Slope_3` | MACD Histogram 3-bar Slope | — | Unbounded | `MACD_Histogram.diff(3)`. Positive = momentum strengthening, negative = weakening. |

---

## Sentiment

| Column | Type | Range | Description |
|---|---|---|---|
| `FnG_Value` | int | 0–100 | Crypto Fear & Greed Index. 0 = Extreme Fear, 100 = Extreme Greed. Daily resolution, same value for all candles in a pipeline run. |
| `FnG_Class` | string | 5 categories | Classification: "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed". `null` if API was unreachable. |

**API source:** `https://api.alternative.me/fng/` (free, no signup, no API key)

---

## Column Count Summary

| Category | Columns | Count |
|---|---|---|
| Trend | SMA x3, EMA x4, Ichimoku x4, ADX/DI x3, Supertrend x2, KAMA, HMA, PSAR, Aroon x3 | 22 |
| Momentum | RSI, StochRSI x2, Stoch x2, MACD x3, Williams %R, CCI, TRIX | 11 |
| Volume | OBV, CMF, MFI | 3 |
| Volatility | BB x2, Donchian x3, ATR, NATR, Parkinson, Realized x2, Vol Ratio, CHOP, Squeeze x2 | 14 |
| Risk | VaR, CVaR, Omega, Tail Ratio, Ulcer Index, Kappa | 6 |
| Price levels | VWAP, Fibonacci x5 | 6 |
| Custom | HDPR x3 | 3 |
| Log returns | 4 periods | 4 |
| Temporal | Hour sin/cos, DOW sin/cos | 4 |
| ML features | Z-scores x3, ratios x3, distances x2, BB Width, slopes x2 | 11 |
| Sentiment | FnG_Value (numeric) | 1 |
| **Total numeric** | | **85** |
| Sentiment (string) | FnG_Class | 1 |
| **Total stored per document** | 85 numeric + 1 string + 5 OHLCV + timestamp + _id | **93 fields** |
