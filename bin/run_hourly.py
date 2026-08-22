#!/usr/bin/env python3
"""
run_hourly.py — Hourly data pipeline launcher (all tokens; count from config.TOKENS).

Runs: spot 1h + perp 1h for all tokens
Schedule: every hour at :05 via com.eeva.tracker-hourly launchd plist
"""

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure we're in the project directory
PROJECT_DIR = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

# Token count is derived from config (not hardcoded) so labels never drift on add/remove.
from btc_tracker_mongodb.config import TOKENS

N_TOKENS = len(TOKENS)

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
        f"\u274c Pipeline: Hourly Update ({N_TOKENS} tokens)\n"
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

MONGO_CONTAINER = "crypto_research_assistant-mongo-1"


def wait_for_mongo(timeout=90, log=None):
    def _log(msg):
        if log is not None:
            log.write(msg + "\n")
            log.flush()

    # Pre-flight: make sure the container is started (idempotent — no-op if running)
    start = subprocess.run(
        ["docker", "start", MONGO_CONTAINER],
        capture_output=True, text=True, timeout=15,
    )
    if start.returncode != 0:
        _log(f"[wait_for_mongo] docker start failed: {start.stderr.strip()}")

    waited = 0
    while waited < timeout:
        result = subprocess.run(
            ["docker", "exec", MONGO_CONTAINER,
             "mongosh", "--eval", "db.adminCommand('ping')", "--quiet"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            _log(f"[wait_for_mongo] mongo ready after {waited}s")
            return True
        time.sleep(2)
        waited += 2
    _log(f"[wait_for_mongo] FAILED after {timeout}s — last stderr: {result.stderr.strip()[:200]}")
    return False


# ── Pipeline steps ──────────────────────────────────────────

# The daily/weekly steps are near-free: `run_update` returns before fetching
# anything unless a new period has closed, so on 23 of 24 runs they are a no-op.
# What they buy is schedule independence. launchd fires on MACHINE LOCAL time,
# so the daily job's 01:10 slot lands at 00:10 UTC under CET but 23:10 UTC under
# CEST — on the wrong side of the UTC day boundary for half the year. Letting the
# hourly job close the day means the completed daily bar lands at 00:05 UTC
# year-round, whatever the daily job's local hour happens to be.
STEPS = [
    # --refresh-last 2 also repairs the hand-over: the last hour written by the
    # old code is a partial bar that is already stored, so the gap check would
    # skip it forever and freeze it wrong. The refresh window rewrites it once
    # the hour has genuinely closed.
    (f"Spot 1h ({N_TOKENS} tokens)",  [VENV_PYTHON, "update.py", "--all", "--timeframe", "1h", "--refresh-last", "2"]),
    (f"Perp 1h ({N_TOKENS} tokens)",  [VENV_PYTHON, "update.py", "--all", "--timeframe", "1h", "--market-type", "perp", "--refresh-last", "2"]),
    (f"Spot daily ({N_TOKENS} tokens)", [VENV_PYTHON, "update.py", "--all", "--timeframe", "1d"]),
    (f"Perp daily ({N_TOKENS} tokens)", [VENV_PYTHON, "update.py", "--all", "--timeframe", "1d", "--market-type", "perp"]),
    (f"Spot weekly ({N_TOKENS} tokens)", [VENV_PYTHON, "update.py", "--all", "--timeframe", "1w"]),
]


def main():
    failed = []

    with open(LOG_FILE, "a") as log:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        log.write(f"\n=== Hourly 1h ({N_TOKENS} tokens) — {ts} ===\n")
        log.flush()

        if not wait_for_mongo(log=log):
            log.write("ABORT: MongoDB not reachable\n")
            log.flush()
            notify_failure("\U0001f5c4 MongoDB not reachable after 90s\n\U0001f527 Is Docker running?")
            sys.exit(1)

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
            f"\U0001fa99 Tokens: {N_TOKENS} (spot + perp 1h)\n"
            f"\u274c Failed: {', '.join(failed)}\n\n"
            f"<pre>{tail[:1000]}</pre>"
        )
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
