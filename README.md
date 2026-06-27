# 🚀 Bitcoin Price Tracker

![Project Title](title_image/ChatGPT%20Image%20May%204,%202025,%2006_09_14%20PM.png)

## 🚀 Project Overview

The **Crypto Price Tracker** is a fully automated data pipeline that fetches daily, weekly, and hourly OHLCV candle data for **BTC, ETH, SOL, XRP, BNB, DOGE, AVAX, LINK, ADA, SUI, DOT, NEAR, PEPE, WIF, SHIB, WLD, ARB** (17 USDT pairs) from KuCoin via CCXT — both **spot** and **perpetual futures** markets — computes 85 technical indicators + ML features, fetches the Fear & Greed Index and funding rates, and stores everything in local Docker MongoDB. Runs on a **Mac Mini M4 Pro** via launchd automation with Telegram alerts. Designed for reliability and zero-downtime operation:

- **Multi-Token, Multi-Market Support**: Tracks 17 tokens across daily + weekly timeframes for spot, plus daily perpetual futures with 8h funding rate history.
- **Perpetual Futures Pipeline**: Fetches perp OHLCV from KuCoin Futures via `ccxt.kucoinfutures`, stores raw 8h funding rates separately for consumer-side aggregation.
- **Historical Seeding**: Backfills up to 500+ candles per token/timeframe in one go.
- **Deep Historical Backfill**: Fetches max available history from KuCoin (back to Oct 2017 for spot daily, Jan 2020 for perp daily) for strategy backtesting.
- **Incremental Updates & Backfill**: Detects and fills any gaps to ensure no candle is ever missed, even if an execution fails.
- **85 Technical Indicators + ML Features**: Trend (SMA, EMA, Ichimoku, ADX, Supertrend, KAMA, HMA, PSAR, Aroon), Momentum (RSI, StochRSI, Stochastic, MACD, Williams %R, CCI, TRIX), Volume (OBV, CMF, MFI), Volatility (Bollinger Bands, Donchian, ATR, NATR, Choppiness, Squeeze Momentum), Risk (VaR, CVaR, Omega Ratio, Tail Ratio, Ulcer Index, Kappa Ratio), plus Z-scores, candle ratios, and momentum slopes — computed from a single source of truth (`indicators.py`). See the full glossary at [`docs/INDICATORS.md`](docs/INDICATORS.md).
- **Local Automation**: Runs via launchd on Mac Mini M4 Pro (daily at 01:10 local + hourly at :05 local). GitHub Actions `workflow_dispatch` kept as manual fallback.
- **Independent Freshness Watchdog**: A third launchd job (`com.eeva.tracker-watchdog`, 07:00 local) reads 85 collections (68 OHLCV + 17 funding_rate) and fires a RED Telegram if any data is stale — catches failure modes where the writers crash silently before their in-script notifier can run.
- **Telegram Alerts**: Daily GREEN confirmation on success, RED alert on failure, weekly GREEN watchdog heartbeat (Sundays).
- **CSV Backup**: Daily export of all collections to `data/` (Time Machine backed up).

This project is written in **Python**, leveraging:

- `ccxt` (pinned to 4.5.40) for KuCoin API access
- `pandas` + `pandas-ta-classic` for data handling and technical analysis
- `pymongo` for seamless MongoDB integration
- `numpy` for numerical computation
- `mcp` for the read-only MCP server (Claude Code integration)

Whether you’re building trading bots, dashboarding price signals, or exploring analytics, this tracker gives you a robust, extensible foundation — zero manual intervention, Telegram alerts on every run, and all data backed up locally + CSV.

## 🔧 Prerequisites

Before you can run the Bitcoin Cloud Price Tracker, make sure you have:

### 1. Accounts & Services

- **KuCoin Account**
  - No API key required — uses public endpoints only (spot + futures).
- **Docker MongoDB** (local)
  - MongoDB 7 running via Docker on `localhost:27017`, database `btc_data`.
  - Collections are created automatically by the seed scripts (e.g. `btc_daily_price_data`, `btc_perp_daily_price_data`, `btc_funding_rate_data`).
  - Shared with Crypto_Research_Assistant (same `btc_data` database).

### 2. Local Tools

- **Python ≥ 3.12**
  - Verify with:
    ```bash
    python --version
    ```
- **pip** (Python package manager)  
  - Usually bundled with Python; upgrade if needed:  
    ```bash
    python -m pip install --upgrade pip
    ```  
- **Git**  
  - For cloning and version-controlling the repo.  

### 3. GitHub (for manual fallback only)

- **Secrets** (Settings → Secrets → Actions): `MONGODB_URI` (points to Atlas for emergency fallback)

### 4. Environment File

Create a `.env` file in the project root:
    ```dotenv
    MONGODB_URI=mongodb://localhost:27017
    TG_BOT_TOKEN=your-telegram-bot-token
    TG_CHAT_ID=your-telegram-chat-id

## 🛠️ Installation & Setup

- **📥 Clone the Repository**  
  - 📂 Run:  
    ```bash
    git clone https://github.com/your-username/btc_price_tracker.git
    cd btc_price_tracker
    ```

- **🐍 Create & Activate Virtual Environment**  
  - ⚙️ macOS/Linux:  
    ```bash
    python -m venv venv
    source venv/bin/activate
    ```  
  - 🖥️ Windows (PowerShell):  
    ```powershell
    python -m venv venv
    .\venv\Scripts\Activate.ps1
    ```

- **📦 Install Python Dependencies**  
  - Ensure you have a `requirements.txt` in the root. Then run:  
    ```bash
    pip install --upgrade pip
    pip install -r requirements.txt
    ```

- **🚀 Seed Historical Data**
  - Seed all 17 tokens with 500 candles each:
    ```bash
    python seed.py --all
    ```
  - Or seed a single token:
    ```bash
    python seed.py --symbol BTC-USDT --timeframe 1h
    ```
  - You should see output like:
    ```
    [seed] BTC-USDT 1h (test=False) - fetching 500 candles...
    [seed] Upserted 301 documents into prod (500 fetched, 301 after NaN drop)
    ```

- **🔍 Verify Seed**
  - Query the latest entries:
    ```bash
    python -m btc_tracker_mongodb.query --symbol BTC-USDT --timeframe 1h --limit 20
    ```

- **🔄 Start Updates**
  - launchd runs daily updates (spot + perp + weekly + CSV backup) at 01:10 local automatically.
  - Run manually for testing:
    ```bash
    python update.py --all --timeframe 1d
    python update.py --all --timeframe 1d --market-type perp
    ```

## ☁️ Architecture & Cloud Deployment

- **🌐 Data Source**
  - KuCoin Public API via CCXT — spot (17 USDT pairs) + KuCoin Futures (17 perp contracts) — no auth required

- **🗄️ Database**
  - Local Docker MongoDB 7 (`localhost:27017`)
  - Database: `btc_data` (~100 collections)
  - Spot collections: `{token}_daily_price_data`, `{token}_weekly_price_data`, `{token}_1h_price_data` (17 daily + 17 weekly + 17 hourly)
  - Perp collections: `{token}_perp_daily_price_data`, `{token}_perp_1h_price_data` (17 daily + 17 hourly)
  - Funding rate collections: `{token}_funding_rate_data` (17 collections, raw 8h granularity)
  - Glossary: `indicator_glossary`, `funding_rate_glossary`, `token_metadata`

- **🐍 Processing Pipeline**
  - `seed.py` — initial backfill (500+ candles per token/timeframe, `--market-type perp` for futures)
  - `backfill.py` — deep historical backfill (max available KuCoin history)
  - `update.py` — incremental updates with gap detection
  - `btc_tracker_mongodb/extract.py` — spot OHLCV fetching via `ccxt.kucoin` (with 429 retry/backoff)
  - `btc_tracker_mongodb/extract_perp.py` — perp OHLCV + funding rate fetching via `ccxt.kucoinfutures`
  - `btc_tracker_mongodb/indicators.py` — 85 indicators + ML features, single source of truth ([glossary](docs/INDICATORS.md))
  - `mcp_server.py` — read-only MCP server for Claude Code integration (7 tools)
  - Dependencies: `ccxt` (pinned 4.5.40), `pandas`, `pandas-ta-classic`, `numpy`, `pymongo`, `mcp`

- **🔄 Automation (launchd on Mac Mini M4 Pro)**

  All times are **local (Europe/Zurich)** — launchd `StartCalendarInterval` fires in machine local time, not UTC.

  - **`com.eeva.tracker-daily`**: 01:10 local daily via `bin/run_daily.py`
    - spot daily → perp daily → spot weekly → CSV backup
    - Telegram GREEN on success, RED on failure
    - Fires at `:10` (offset from hourly `:05`) to avoid `wait_for_mongo()` collision on the shared Docker container
  - **`com.eeva.tracker-hourly`**: every hour at :05 local via `bin/run_hourly.py`
    - All 17 tokens spot 1h + perp 1h, Telegram RED on failure only
  - **`com.eeva.tracker-watchdog`**: 07:00 local daily via `bin/run_watchdog.py`
    - Independent freshness check — reads 85 collections (68 OHLCV + 17 funding_rate)
    - Thresholds: 36h for daily/perp-daily, 3h for 1h/perp-1h
    - Telegram RED on any stale collection; GREEN heartbeat on Sundays; "Watchdog Self-Error" RED if the watchdog itself crashes
    - Covers silent failure modes where the writer dies before its in-script notifier can run (e.g., launchd `posix_spawn` errors, Docker down, Python import failures)
  - **Fallback**: GitHub Actions `workflow_dispatch` (manual trigger, writes to Atlas)
  - **Logs**: Date-stamped in `logs/` (daily 30-day retention, hourly 14-day, watchdog per-day)

- **🔒 Secrets Management**
  - **Local `.env`**: `MONGODB_URI`, `TG_BOT_TOKEN`, `TG_CHAT_ID`
  - **GitHub Secrets**: `MONGODB_URI` (Atlas, for manual fallback only)

- **🤖 MCP Server (Claude Code Integration)**
  - `mcp_server.py` exposes 7 read-only tools for querying MongoDB directly from Claude Code conversations
  - Registered via `.mcp.json` — auto-discovered when Claude Code opens the project
  - Tools: `list_collections`, `query_price_data`, `get_latest_price`, `get_indicator_glossary`, `get_collection_stats`, `query_by_date_range`, `query_funding_rates`
  - Supports `market_type="spot"` or `"perp"` on price data tools
  - All tools accept flexible symbol input (`"BTC"`, `"btc"`, or `"BTC-USDT"`) and return JSON
  - Uses stdio transport; reuses existing `db.py` connection and config constants

- **✅ Resilience & Backfill**
  - Automatic gap detection backfills missed candles for all tokens
  - Bulk upsert with unique timestamp index prevents duplicates

## 📈 Usage & Examples

- **👟 Running Locally**

  - Activate your virtual env (if not already): 
 
    ```bash
    source venv/bin/activate      # macOS/Linux  
    .\venv\Scripts\Activate.ps1   # Windows PowerShell  
    ```
 
  - Run the update script manually:

    ```bash
    python update.py --all --timeframe 1h
    ```
  - You should see console output like:
    ```
    [update] BTC-USDT 1h - gap from 2026-03-01 22:00:00+00:00 to 2026-03-01 23:00:00+00:00
    [update] Upserted 1 new candles for BTC-USDT 1h
    [update] ETH-USDT 1h - up to date (latest: 2026-03-01 23:00:00+00:00)
    ```

- **⏳ Backfill Gaps**
  - If the script detects missed candles (e.g. downtime), it automatically fetches and inserts all missing candles for every token.

- **📜 Deep Historical Backfill**
  - Fetch max available history from KuCoin for backtesting:
    ```bash
    python backfill.py --all --timeframe 1d --skip-btc        # all altcoins, spot daily
    python backfill.py --all --timeframe 1d --market-type perp # all tokens, perp daily
    python backfill.py --all --timeframe 1w                    # all tokens, spot weekly
    python backfill.py --all --test --dry-run                  # preview without writing
    ```
  - Default start dates: Oct 2017 (spot daily/weekly), Jan 2020 (perp). Override with `--since`.
  - Safe to re-run — upsert semantics handle duplicates. Per-token error isolation.

- **📊 Querying the Database**
  - Inspect the latest candles:
    ```bash
    python -m btc_tracker_mongodb.query --symbol BTC-USDT --timeframe 1h --limit 20
    python -m btc_tracker_mongodb.query --symbol ETH-USDT --timeframe 1d --limit 10
    ```
  - View the indicator glossary (descriptions, ranges, categories):
    ```bash
    python -m btc_tracker_mongodb.query --glossary
    ```
  - Sample output (timestamps descending):  
    | timestamp              | Open     | High     | Low      | Close    | Volume    |
    |------------------------|----------|----------|----------|----------|-----------|
    | 2025-05-05T14:00:00Z   | 96410.35 | 96500.00 | 96300.00 | 96475.70 | 28.45     |
    | 2025-05-05T13:00:00Z   | 96300.21 | 96420.10 | 96210.50 | 96390.11 | 22.18     |
    | …                      | …        | …        | …        | …        | …         |

- **🔧 Integrating with Your Dashboard**  
  - Connect directly to MongoDB Atlas from your visualization tool (e.g. Metabase, Grafana, Tableau).  
  - Use the `timestamp` index and indicator fields (e.g. `EMA_20`, `RSI`, `MACD_Line`, `ATR_14`, `ADX_14`) to build charts & alerts.

- **🤖 Extending for Trading Bots**
  - Read the latest document before placing orders:
    ```python
    from pymongo import MongoClient
    client = MongoClient(os.getenv("MONGODB_URI"))
    btc_1h = client["btc_data"]["btc_1h_price_data"]
    latest = btc_1h.find_one({}, sort=[("timestamp", -1)])
    print(latest["RSI"], latest["ATR_14"], latest["ADX_14"], latest["MACD_Histogram"])
    ```
  - Incorporate signals (e.g. `HDPR_Signal`, `Williams_R_14`, `Vol_Ratio_14_30`) into your strategy logic.

- **🤖 MCP Server (Claude Code)**
  - The MCP server is auto-discovered by Claude Code via `.mcp.json` — no manual setup needed.
  - Once connected, Claude Code can query your MongoDB data directly in conversation using 7 tools:

    | Tool | What it does |
    |------|-------------|
    | `list_collections()` | Lists all collections (spot, perp, funding, weekly) |
    | `query_price_data(symbol, timeframe, limit, fields, market_type)` | Latest N docs, `market_type="spot"` or `"perp"` |
    | `get_latest_price(symbol, timeframe, market_type)` | Single most recent document |
    | `get_indicator_glossary()` | Indicator descriptions, categories, and ranges |
    | `get_collection_stats(symbol, timeframe, market_type)` | Doc count, date range, column list |
    | `query_by_date_range(symbol, start, end, timeframe, fields, limit, market_type)` | Query within a date range |
    | `query_funding_rates(symbol, limit, start_date, end_date)` | 8h funding rate history |

  - All tools accept flexible symbol input: `"BTC"`, `"btc"`, or `"BTC-USDT"` all work.
  - Requires `MONGODB_URI` in `.env` (same as the rest of the project).

- **📦 Docker Usage**
  - Build & run via Docker (for local testing):
    ```bash
    docker build -t btc-tracker .
    docker run --env-file .env btc-tracker
    ```
  - The container starts a Flask HTTP endpoint at port 8080 (legacy; primary automation is launchd on Mac Mini).

Enjoy exploring and building on top of your live, cloud‐hosted Bitcoin price tracker!  

## 🛠️ Development & Testing

- **🐍 Virtual Environment**  
  - Always activate your `venv` before coding or testing:  
    ```bash
    source venv/bin/activate      # macOS/Linux  
    .\venv\Scripts\Activate.ps1   # Windows PowerShell  
    ```  

- **🧪 Unit Tests with pytest**  
  - Install pytest:  
    ```bash
    pip install pytest
    ```  
  - Create `tests/` folder alongside your scripts.  
  - Example test for `fetch_missing_candles()` in `tests/test_backfill.py`:  
    ```python
    import time
    from btc_tracker_mongodb.extract import fetch_candles
    import time

    def test_fetch_btc_candles():
        now_ms = int(time.time() * 1000)
        since_ms = now_ms - (5 * 3600 * 1000)  # last 5 hours
        df = fetch_candles("BTC-USDT", "1h", since_ms, limit=5)
        assert len(df) >= 3
        assert "Open" in df.columns
        assert "Close" in df.columns
    ```  
  - Run all tests:  
    ```bash
    pytest --maxfail=1 --disable-warnings -q
    ```  

- **🐛 Debugging & Logging**  
  - Sprinkle `print()` or use Python’s `logging` module at key steps:  
    ```python
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logging.debug(f"Backfilling from {start_ts} to {end_ts}")
    ```  
  - Tail logs when running locally:  
    ```bash
    tail -f update.log
    ```  

- **🔍 Lint & Format**  
  - Enforce style with **black** and **flake8**:  
    ```bash
    pip install black flake8
    black .
    flake8 .
    ```  

- **📦 Docker Build Test**  
  - Verify your `Dockerfile` builds without errors:  
    ```bash
    docker build -t btc-tracker:test .
    docker run --rm btc-tracker:test --help
    ```  

- **🗄️ Use a Dev Database**  
  - Point to a separate “dev” Atlas cluster by using a `.env.dev` file:  
    ```dotenv
    MONGODB_URI="mongodb+srv://dev-user:…@dev-cluster.mongodb.net/btc_data_dev"
    ```  
  - Load it in your session:  
    ```bash
    cp .env.dev .env
    ```  

- **🎯 End-to-End Smoke Test**  
  - After seeding, run the full update and query scripts in one go:
    ```bash
    python seed.py --symbol BTC-USDT --timeframe 1h
    python update.py --symbol BTC-USDT --timeframe 1h
    python -m btc_tracker_mongodb.query --symbol BTC-USDT --timeframe 1h --limit 5
    ```
  - Confirm the latest timestamp in the output matches “now” floored to the hour.

- **🌐 Continuous Integration**  
  - Add your pytest, lint, and build steps to your GitHub Actions workflow to catch issues early:  
    ```yaml
    - name: Run tests & lint
      run: |
        pip install pytest black flake8
        pytest --maxfail=1 --disable-warnings -q
        black --check .
        flake8 .
    ```  

With these practices in place, you’ll have a rock-solid development workflow and confidence that every change preserves data integrity.  

## 🔒 Security & Secrets Management

- **🗝️ Secrets Storage**  
  - **GitHub Secrets**: Store `MONGODB_URI` in **Settings → Secrets → Actions**. No KuCoin API keys needed (public endpoints only).  
  - **Local `.env`**: Keep your `.env` file out of version control; confirm `.gitignore` includes `.env`.  

- **🔑 Key Rotation**  
  - Rotate API keys regularly (e.g. every 90 days).  
  - After rotation, immediately update your GitHub Secrets and redeploy.  

- **🔒 Principle of Least Privilege**  
  - **MongoDB User**: Grant only `readWrite` on the `btc_data` database.  
  - **KuCoin API**: Enable only “spot market data” permissions; disable trading/withdrawals if not required.  

- **🌐 Network Security**  
  - **Atlas IP Whitelisting**: Restrict access to known IPs (e.g. your office IP or GitHub Actions IP range).  
  - **Private Endpoints / VPC Peering** (optional): Connect your runners via a private network link for extra isolation.  

- **🔐 Encryption**  
  - **In Transit**: All MongoDB connections via TLS; all API calls via HTTPS.  
  - **At Rest**: Atlas free-tier includes encryption at rest by default.  

- **🛡️ Audit & Monitoring**  
  - Enable **MongoDB Atlas Auditing** to track connections and data changes.  
  - Review GitHub Actions run logs and Atlas logs for unusual activity.  

- **💡 Best Practices**  
  - Never commit secrets or `.env` files to source control.  
  - Use separate credentials for development vs. production environments.  
  - Document your key rotation and incident response procedures.  

- **🚨 Incident Response**  
  - Immediately revoke any compromised API keys.  
  - Audit recent MongoDB operations and API access logs.  
  - Regenerate and update secrets, then redeploy your workflows within minutes.  

## ⚙️ CI/CD Workflow

- **🛠️ GitHub Actions Workflows**
  - `update-daily.yml`: manual `workflow_dispatch` only (cron disabled — runs via launchd on Mac Mini)
  - `update-hourly.yml`: manual `workflow_dispatch` only (cron disabled)
  - Secret: `MONGODB_URI` (points to Atlas for emergency fallback)
  - **Note:** Cron schedules disabled since 2026-04-04. Primary automation is launchd on Mac Mini M4 Pro.

- **🔄 Core Steps**
  1. **📥 Checkout** your repo
  2. **🐍 Setup Python** 3.11 (CI) / 3.12 (local)
  3. **📦 Install deps** (`pip install -r requirements.txt`)
  4. **🚀 Run updaters** (spot daily → perp daily → spot weekly)
     ```yaml
     - name: Run daily update for all tokens (spot)
       run: python update.py --all --timeframe 1d
     - name: Run daily update for all tokens (perp)
       run: python update.py --all --timeframe 1d --market-type perp
     - name: Run weekly update for all tokens (spot)
       run: python update.py --all --timeframe 1w
     ```

- **🎯 Build & Deploy (Optional)**  
  If you choose Cloud Run instead of pure Actions:  
  - **🐳 Build & push** via `gcloud builds submit --tag gcr.io/...`  
  - **☁️ Deploy** with `gcloud run deploy ...`  
  - **📆 Schedule** with Cloud Scheduler  

- **📈 Monitoring & Alerts**  
  - View GitHub Action run history & logs under **Actions** tab.  
  - Enable GitHub **branch protection** to require green builds before merging.  
  - (Optional) Integrate with Slack or email via GitHub webhooks for failure alerts.  

With this automation in place, launchd on the Mac Mini fetches, computes, and upserts candles for all 17 tokens daily — fully hands-off and production-ready!  

## ❓ Troubleshooting & FAQs

- **⚠️ “No data for BTC-USDT 1h — run seed first.”**
  - The update script requires at least 200 rows to compute long-window indicators.
  - **Solution**: Run `python seed.py --symbol BTC-USDT --timeframe 1h` to seed 500 candles first.

- **❌ “Service unavailable from a restricted location”**  
  - This error was triggered by Binance geo‐blocks on cloud egress IPs.  
  - **Solution**: You’re now using KuCoin’s public API—make sure your code is up to date and you’re not accidentally calling Binance endpoints.

- **🐛 “Skipping upsert: NaNs in indicators”**  
  - Indicates some long‐window indicators (e.g. SMA_200, EMA_200) still have insufficient data.  
  - **Solution**:  
    1. Verify your DataFrame contains at least 200+ rows.  
    2. Re‐run `seed.py` or let the hourly backfill accumulate more hours.

- **🔒 “MONGODB_URI not set” or authentication errors**
  - Happens when `MONGODB_URI` is unset or invalid.
  - **Solution**:
    - Locally: Confirm `.env` file in project root contains `MONGODB_URI` (and is listed in `.gitignore`).
    - GitHub Actions: Check **Settings → Secrets** for the `MONGODB_URI` secret.

- **🐢 Performance issues or rate limits**  
  - KuCoin’s public API allows ~300 requests/min. Backfill uses one request per range call.  
  - **Solution**:  
    - For large backfills, split into smaller chunks (e.g. 250h at a time).  
    - Add short `time.sleep(1)` between calls if you hit HTTP 429.

- **🤔 FAQs**  
  - **Q**: _How do I start over (reset the database)?_
    **A**: In MongoDB Atlas, drop the collection (e.g. `btc_1h_price_data`), then run `python seed.py --symbol BTC-USDT --timeframe 1h`.
  - **Q**: _Can I track other timeframes (e.g. 15m)?_
    **A**: The tracker already supports 1h, 4h, and 1d. To add more, add the timeframe to `TIMEFRAMES` in `btc_tracker_mongodb/config.py`, update `extract.py` mappings, and run the seed.
  - **Q**: _How do I add a new token?_
    **A**: Add the symbol to `TOKENS` in `btc_tracker_mongodb/config.py` (e.g. `"ATOM-USDT"`) and seed it with `python seed.py --symbol ATOM-USDT --all-timeframes`. GitHub Actions will pick it up automatically.
  - **Q**: _How do I add a custom indicator?_
    **A**:
      1. Add the computation to `btc_tracker_mongodb/indicators.py` (in `compute_all()`).
      2. Add the column to `INDICATOR_GLOSSARY` in `indicators.py` (`get_numeric_cols()` derives from it automatically).
      3. Add the column to [`docs/INDICATORS.md`](docs/INDICATORS.md) glossary.
      4. That's it — all scripts use `indicators.py` as the single source of truth, and the MongoDB glossary auto-syncs on the next pipeline run.
  - **Q**: _How can I visualize the data?_  
    **A**: Connect your visualization tool (Metabase, Grafana, Tableau) to your Atlas cluster using the same `MONGODB_URI`. Use the `timestamp` index and any indicator fields for charts.  

## ✨ Contributors & License

- **👩‍💻 Lead Developer**  
  - Swissbit92 ([GitHub](https://github.com/Swissbit92))  

- **🤖 AI Assistant**  
  - ChatGPT by OpenAI (code generation, documentation, and guidance)  

- **🛠️ Contributions Welcome**  
  - Fork the repo, create a feature branch, submit a Pull Request.  
  - 🤝 Please adhere to the existing code style and add tests for new functionality.  

- **📄 License**  
  This project is released under the **MIT License**:  
  ```text
  MIT License

  Copyright (c) 2025 Swissbit92

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in all
  copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
  SOFTWARE.
