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
