#!/usr/bin/env python3
"""
run_hourly.py — Hourly data pipeline launcher (all 18 tokens).

Runs: spot 1h + perp 1h for all tokens
Schedule: every hour at :05 via com.eeva.tracker-hourly launchd plist
"""

import os
import sys
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure we're in the project directory
PROJECT_DIR = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_DIR)

# Load .env
from dotenv import load_dotenv
load_dotenv(PROJECT_DIR / ".env")

VENV_PYTHON = str(PROJECT_DIR / "venv" / "bin" / "python")
LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"hourly-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"
HEADER_IMAGE = PROJECT_DIR / "images" / "PriceTracker_01.png"
HOSTNAME = os.uname().nodename.split(".")[0]

# Clean old logs (14 days)
for f in LOG_DIR.glob("hourly-*.log"):
    if f.stat().st_mtime < time.time() - 14 * 86400:
        f.unlink(missing_ok=True)


# ── Telegram helper ─────────────────────────────────────────

def notify_failure(detail):
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        return

    import requests
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = (
        f"\U0001f6a8 Price Tracker Alert \U0001f6a8\n\n"
        f"\u23f0 {ts}\n"
        f"\U0001f5a5 {HOSTNAME}\n\n"
        f"\u274c Pipeline: Hourly Update (18 tokens)\n"
        f"\u26a0\ufe0f Status: FAILED\n\n"
        f"{detail}\n\n"
        f"\U0001f527 Check logs for details\n"
        f"\U0001f525 #Crypto #Eeva #PriceTracker"
    )
    try:
        photo = str(HEADER_IMAGE) if HEADER_IMAGE.is_file() else None
        if photo:
            with open(photo, "rb") as f:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": msg[:1024], "parse_mode": "HTML"},
                    files={"photo": f},
                    timeout=20,
                )
        else:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
                timeout=20,
            )
    except Exception:
        pass


# ── Docker/MongoDB readiness check ─────────────────────────

def wait_for_mongo(timeout=30):
    waited = 0
    while waited < timeout:
        result = subprocess.run(
            ["docker", "exec", "crypto_research_assistant-mongo-1",
             "mongosh", "--eval", "db.adminCommand('ping')", "--quiet"],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            return True
        time.sleep(2)
        waited += 2
    return False


# ── Pipeline steps ──────────────────────────────────────────

STEPS = [
    ("Spot 1h (18 tokens)",  [VENV_PYTHON, "update.py", "--all", "--timeframe", "1h"]),
    ("Perp 1h (18 tokens)",  [VENV_PYTHON, "update.py", "--all", "--timeframe", "1h", "--market-type", "perp"]),
]


def main():
    if not wait_for_mongo():
        notify_failure("\U0001f5c4 MongoDB not reachable after 30s\n\U0001f527 Is Docker running?")
        sys.exit(1)

    failed = []

    with open(LOG_FILE, "a") as log:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        log.write(f"\n=== Hourly 1h (18 tokens) — {ts} ===\n")
        log.flush()

        for name, cmd in STEPS:
            result = subprocess.run(cmd, stdout=log, stderr=log, cwd=str(PROJECT_DIR))
            if result.returncode != 0:
                failed.append(name)

    if failed:
        try:
            tail = "\n".join(LOG_FILE.read_text().splitlines()[-12:])
        except Exception:
            tail = "(no log)"
        notify_failure(
            f"\U0001fa99 Token: BTC-USDT\n"
            f"\u274c Failed: {', '.join(failed)}\n\n"
            f"<pre>{tail[:1000]}</pre>"
        )
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
