# 🚀 Bitcoin Cloud Price Tracker

![Project Title](title_image/ChatGPT%20Image%20May%204,%202025,%2006_09_14%20PM.png)

## 🚀 Project Overview

The **Bitcoin Cloud Price Tracker** is a fully automated, cloud‐hosted application that fetches hourly BTC/USDT price data from the KuCoin public API, computes a comprehensive suite of technical indicators, and stores everything in a MongoDB Atlas database. Designed for reliability and zero‐downtime operation, it handles:

- **Historical Seeding**: Backfills up to 500 hours of past data in one go.  
- **Hourly Updates & Backfill**: Detects and fills any gaps to ensure no candle is ever missed, even if an execution fails.  
- **Technical Analysis**: Calculates moving averages (SMA, EMA), momentum indicators (RSI, StochRSI), volatility bands (Bollinger, Donchian), Ichimoku Cloud, Fibonacci retracements, moon phases, HDPR signals, MACD, and more—right in the database.  
- **Serverless Execution**: Runs on GitHub Actions (or optionally on GCP Cloud Run + Scheduler) without the need for a dedicated VM.  

This project is written in **Python**, leveraging:

- `requests` for API calls  
- `pandas` for data handling  
- `ta` for technical indicators  
- `skyfield` for astronomical calculations  
- `pymongo` for seamless MongoDB integration  

Whether you’re building trading bots, dashboarding price signals, or simply exploring on‐chain analytics, this tracker gives you a robust, extensible foundation—no local host required, zero manual intervention, and all data safely in the cloud.  

## 🔧 Prerequisites

Before you can run the Bitcoin Cloud Price Tracker, make sure you have:

### 1. Accounts & Services

- **KuCoin Account**  
  - Create a free KuCoin account and generate an API key & secret (no IP‐whitelist).  
- **MongoDB Atlas**  
  - Sign up for the free tier, create a cluster, a database named `btc_data`, and a collection `1h_price_data`.  
  - Create a database user with read/write permissions.  

### 2. Local Tools

- **Python ≥ 3.10**  
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

### 3. GitHub (if using Actions)

- **Repository**  
  - Fork or push this project to your GitHub account.  
- **Secrets** (Settings → Secrets → Actions)  
  - `MONGODB_URI`  
  - `KUCOIN_API_KEY`  
  - `KUCOIN_API_SECRET`  
  - _(Optional)_ `KUCOIN_PASSPHRASE`  

### 4. Environment File (if running locally)

Create a `.env` file in the project root:
    ```dotenv
    MONGODB_URI="your-atlas-uri"
    KUCOIN_API_KEY="your-kucoin-api-key"
    KUCOIN_API_SECRET="your-kucoin-api-secret"
    # KUCOIN_PASSPHRASE="your-kucoin-passphrase"   # only if you set one

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
  - This populates MongoDB with the last 500 hourly candles + indicators:  
    ```bash
    python seed_historical.py
    ```  
  - ✅ You should see a confirmation like:
    ```
    ✅ Seeded 500 hourly candles with indicators (newest first)
    ```

- **🔍 Verify Seed**  
  - Run the query script to inspect the latest 100 entries:  
    ```bash
    python query_latest_100.py
    ```  
  - You should see timestamps descending and all OHLCV fields present.

- **🔄 Start Hourly Updates**  
  - If using **GitHub Actions**, your workflow is preconfigured in:  
    ```
    .github/workflows/update-hourly.yml
    ```  
  - Ensure your GitHub **Secrets** (`MONGODB_URI`, `KUCOIN_API_KEY`, `KUCOIN_API_SECRET`) are set.  
  - You can also run manually for testing:  
    ```bash
    python btc_tracker_mongodb/update_hourly.py
    ```

## ☁️ Architecture & Cloud Deployment

- **🌐 Data Source**  
  - KuCoin Public API (1h BTC-USDT candles, no auth required)  

- **🗄️ Cloud Database**  
  - MongoDB Atlas (Free tier M0)  
  - Database: `btc_data`, Collection: `1h_price_data`  

- **🐍 Processing Scripts**  
  - `seed_historical.py` – backfills last 500h of data  
  - `update_hourly.py` – hourly incremental & backfill updates  
  - Dependencies: `pandas`, `ta`, `skyfield`, `requests`, `pymongo`  

- **🔄 Automation & CI/CD**  
  - **GitHub Actions**  
    - Workflow: `.github/workflows/update-hourly.yml`  
    - Schedule: cron `0 * * * *` (hourly)  
    - Steps:  
      - Checkout code  
      - Setup Python 3.10  
      - Install dependencies  
      - Run `update_hourly.py`  
  - **⚙️ (Optional) GCP Cloud Run + Cloud Scheduler**  
    - Containerized service via `Dockerfile`  
    - Cloud Scheduler job issues HTTP GET to service hourly  

- **🔒 Secrets Management**  
  - **GitHub Secrets**: `MONGODB_URI`, `KUCOIN_API_KEY`, `KUCOIN_API_SECRET`  
  - **Local .env** for development  

- **✅ Resilience & Backfill**  
  - Automatic delta detection backfills missed hours  
  - Single-range fetch ensures data continuity even after outages  

## 📈 Usage & Examples

- **👟 Running Locally**  
  - Activate your virtual env (if not already):  
    ```bash
    source venv/bin/activate      # macOS/Linux  
    .\venv\Scripts\Activate.ps1   # Windows PowerShell  
    ```  
  - Run the hourly update script manually:  
    ```bash
    python btc_tracker_mongodb/update_hourly.py
    ```  
  - You should see console output like:  
    ```
    ✅ Upserted backfilled candle @ 2025-05-05 14:00:00+00:00
    ```  

- **⏳ Backfill Gaps**  
  - If the script detects missed hours (e.g. downtime), it will fetch and insert all missing candles between the last stored timestamp and now.  
  - Example output when 3 hours are backfilled:  
    ```
    ✅ Upserted backfilled candle @ 2025-05-05 12:00:00+00:00  
    ✅ Upserted backfilled candle @ 2025-05-05 13:00:00+00:00  
    ✅ Upserted backfilled candle @ 2025-05-05 14:00:00+00:00  
    ```  

- **📊 Querying the Database**  
  - Inspect the latest 100 hourly candles via the provided script:  
    ```bash
    python query_latest_100.py
    ```  
  - Sample output (timestamps descending):  
    | timestamp              | Open     | High     | Low      | Close    | Volume    |
    |------------------------|----------|----------|----------|----------|-----------|
    | 2025-05-05T14:00:00Z   | 96410.35 | 96500.00 | 96300.00 | 96475.70 | 28.45     |
    | 2025-05-05T13:00:00Z   | 96300.21 | 96420.10 | 96210.50 | 96390.11 | 22.18     |
    | …                      | …        | …        | …        | …        | …         |

- **🔧 Integrating with Your Dashboard**  
  - Connect directly to MongoDB Atlas from your visualization tool (e.g. Metabase, Grafana, Tableau).  
  - Use the `timestamp` index and indicator fields (e.g. `EMA_20`, `RSI`, `MACD_Line`) to build charts & alerts.

- **🤖 Extending for Trading Bots**  
  - Read the latest document before placing orders:  
    ```python
    latest = collection.find_one({}, sort=[("timestamp", -1)])
    print(latest["RSI"], latest["EMA_50"], latest["MACD_Histogram"])
    ```  
  - Incorporate signals (e.g. `HDPR_Signal`) into your strategy logic.

- **📦 Docker Usage**  
  - Build & run via Docker (for local testing):  
    ```bash
    docker build -t btc-tracker .  
    docker run --env-file .env btc-tracker  
    ```  
  - The container starts a Flask HTTP endpoint at port 8080 (used by Cloud Run).  

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
    from btc_tracker_mongodb.update_hourly import fetch_missing_candles
    from datetime import datetime, timezone, timedelta

    def test_fetch_3h_backfill():
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        start = int((now - timedelta(hours=3)).timestamp())
        end   = int(now.timestamp())
        candles = fetch_missing_candles(start, end)
        assert isinstance(candles, list)
        assert len(candles) >= 3
        # each entry has timestamp and numeric fields
        for c in candles:
            assert "timestamp" in c
            assert isinstance(c["Open"], float)
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
    python seed_historical.py
    python update_hourly.py
    python query_latest_100.py
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
  - **GitHub Secrets**: Store `MONGODB_URI`, `KUCOIN_API_KEY`, `KUCOIN_API_SECRET` in **Settings → Secrets → Actions**.  
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

- **🛠️ GitHub Actions Workflow**  
  - File: `.github/workflows/update-hourly.yml`  
  - Triggers:  
    - ⏰ `schedule: "0 * * * *"` (hourly)  
    - ⚡ `workflow_dispatch` (manual)  
  - Env-secrets (Settings → Secrets → Actions):  
    - `MONGODB_URI`  
    - `KUCOIN_API_KEY`  
    - `KUCOIN_API_SECRET`  

- **🔄 Core Steps**  
  1. **📥 Checkout** your repo  
  2. **🐍 Setup Python** 3.10  
  3. **📦 Install deps** (`pymongo[srv]`, `python-dotenv`, `pandas`, `ta`, `skyfield`, `requests`)  
  4. **🧪 (Optional) Lint & Test**  
     ```yaml
     - name: Run tests & lint
       run: |
         pip install pytest black flake8
         pytest --maxfail=1 --disable-warnings -q
         black --check .
         flake8 .
     ```  
  5. **🚀 Run updater**  
     ```yaml
     - name: Run hourly update
       run: python btc_tracker_mongodb/update_hourly.py
       env:
         MONGODB_URI:      ${{ secrets.MONGODB_URI }}
         KUCOIN_API_KEY:   ${{ secrets.KUCOIN_API_KEY }}
         KUCOIN_API_SECRET:${{ secrets.KUCOIN_API_SECRET }}
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

With this CI/CD pipeline in place, every push or scheduled run will automatically fetch, compute, and upsert your BTC/USDT candles—fully hands-off and production-ready!  

## ❓ Troubleshooting & FAQs

- **⚠️ “Expected 200 rows, found X”**  
  - Your `update_hourly.py` requires at least 200 historical rows to compute long‐window indicators.  
  - **Solution**: Run `python seed_historical.py` to seed 500 hours, or ensure you’ve backfilled enough data.

- **❌ “Service unavailable from a restricted location”**  
  - This error was triggered by Binance geo‐blocks on cloud egress IPs.  
  - **Solution**: You’re now using KuCoin’s public API—make sure your code is up to date and you’re not accidentally calling Binance endpoints.

- **🐛 “Skipping upsert: NaNs in indicators”**  
  - Indicates some long‐window indicators (e.g. SMA_200, EMA_200) still have insufficient data.  
  - **Solution**:  
    1. Verify your DataFrame contains at least 200+ rows.  
    2. Re‐run `seed_historical.py` or let the hourly backfill accumulate more hours.

- **🔒 “Authentication failed” or missing environment variables**  
  - Happens when `MONGODB_URI`, `KUCOIN_API_KEY`, or `KUCOIN_API_SECRET` are unset or invalid.  
  - **Solution**:  
    - Locally: Confirm `.env` file in project root contains correct entries (and is listed in `.gitignore`).  
    - GitHub Actions: Check **Settings → Secrets** for typos and that they match your workflow.

- **🐢 Performance issues or rate limits**  
  - KuCoin’s public API allows ~300 requests/min. Backfill uses one request per range call.  
  - **Solution**:  
    - For large backfills, split into smaller chunks (e.g. 250h at a time).  
    - Add short `time.sleep(1)` between calls if you hit HTTP 429.

- **🤔 FAQs**  
  - **Q**: _How do I start over (reset the database)?_  
    **A**: In MongoDB Atlas, drop the `1h_price_data` collection, then run `python seed_historical.py`.  
  - **Q**: _Can I track other timeframes (e.g. 15m, 4h)?_  
    **A**: Yes—duplicate and adapt `fetch_missing_candles()` and `fetch_latest_candle()` with the desired `type` (e.g. `"15min"`, `"4hour"`). Then adjust your MongoDB schema accordingly.  
  - **Q**: _How do I add a custom indicator?_  
    **A**:  
      1. Import or implement the indicator in `update_hourly.py` (or `seed_historical.py`).  
      2. Compute it on the DataFrame alongside the other indicators.  
      3. Add its column name to the `numeric_cols` list so NaN checks still apply.  
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
