#!/usr/bin/env python3
"""
run_daily.py — Daily data pipeline launcher (replaces btc-daily.sh for launchd).

Runs: spot daily + perp daily + spot weekly + CSV export
Schedule: 01:05 UTC daily via com.eeva.tracker-daily launchd plist
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
LOG_FILE = LOG_DIR / f"daily-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"
HEADER_IMAGE = PROJECT_DIR / "images" / "PriceTracker_01.png"
HOSTNAME = os.uname().nodename.split(".")[0]

# Clean old logs (30 days)
for f in LOG_DIR.glob("daily-*.log"):
    if f.stat().st_mtime < time.time() - 30 * 86400:
        f.unlink(missing_ok=True)


# ── Telegram helpers ────────────────────────────────────────

def _send_telegram(message, photo_path=None):
    """Send Telegram message, optionally with photo."""
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        return

    import requests
    try:
        if photo_path and Path(photo_path).is_file():
            caption = message[:1024]
            remainder = message[1024:] if len(message) > 1024 else ""
            with open(photo_path, "rb") as f:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"photo": f},
                    timeout=20,
                )
            if remainder:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": remainder, "parse_mode": "HTML"},
                    timeout=20,
                )
        else:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                timeout=20,
            )
    except Exception:
        pass  # Notification failure should never crash the pipeline


def notify_success(steps_passed, steps_total, duration, token_count):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = (
        f"\U0001f4ca Daily Price Update \U0001f4ca\n\n"
        f"\u23f0 {ts}\n"
        f"\U0001f5a5 {HOSTNAME}\n\n"
        f"\u2705 Pipeline: Daily Update\n\n"
        f"\U0001f3c6 Results:\n"
        f"\u2022 \U0001f4c8 Steps: {steps_passed}/{steps_total} passed\n"
        f"\u2022 \U0001fa99 Tokens: {token_count}\n"
        f"\u2022 \u23f1 Duration: {duration}\n\n"
        f"\U0001f4aa Data fresh & backed up! \U0001f48e\n"
        f"\U0001f525 #Crypto #Eeva #PriceTracker"
    )
    photo = str(HEADER_IMAGE) if HEADER_IMAGE.is_file() else None
    _send_telegram(msg, photo)


def notify_failure(detail):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = (
        f"\U0001f6a8 Price Tracker Alert \U0001f6a8\n\n"
        f"\u23f0 {ts}\n"
        f"\U0001f5a5 {HOSTNAME}\n\n"
        f"\u274c Pipeline: Daily Update\n"
        f"\u26a0\ufe0f Status: FAILED\n\n"
        f"{detail}\n\n"
        f"\U0001f527 Check logs for details\n"
        f"\U0001f525 #Crypto #Eeva #PriceTracker"
    )
    photo = str(HEADER_IMAGE) if HEADER_IMAGE.is_file() else None
    _send_telegram(msg, photo)


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

STEPS = [
    (f"Spot daily ({N_TOKENS} tokens)", [VENV_PYTHON, "update.py", "--all", "--timeframe", "1d"]),
    (f"Perp daily ({N_TOKENS} tokens)", [VENV_PYTHON, "update.py", "--all", "--timeframe", "1d", "--market-type", "perp"]),
    (f"Spot weekly ({N_TOKENS} tokens)", [VENV_PYTHON, "update.py", "--all", "--timeframe", "1w"]),
    ("CSV backup",             [VENV_PYTHON, "export_data.py"]),
]


def main():
    started = time.time()
    failed = []
    steps_passed = 0

    with open(LOG_FILE, "a") as log:
        run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        log.write(f"\n===== Daily run started {run_ts} UTC =====\n")
        log.flush()

        if not wait_for_mongo(log=log):
            log.write("ABORT: MongoDB not reachable\n")
            log.flush()
            notify_failure("\U0001f5c4 MongoDB not reachable after 90s\n\U0001f527 Is Docker running?")
            sys.exit(1)

        for i, (name, cmd) in enumerate(STEPS, 1):
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            log.write(f"\n=== Step {i}: {name} — {ts} ===\n")
            log.flush()

            result = subprocess.run(cmd, stdout=log, stderr=log, cwd=str(PROJECT_DIR))
            if result.returncode == 0:
                steps_passed += 1
            else:
                failed.append(name)

    elapsed = int(time.time() - started)
    duration = f"{elapsed // 60}m {elapsed % 60}s"

    if failed:
        # Read last 20 lines of log for error context
        try:
            tail = "\n".join(LOG_FILE.read_text().splitlines()[-20:])
        except Exception:
            tail = "(no log)"
        notify_failure(
            f"\U0001f4c8 Steps: {steps_passed}/{len(STEPS)} passed\n"
            f"\u274c Failed:\n" + "\n".join(f"  \u2022 {f}" for f in failed) +
            f"\n\u23f1 Duration: {duration}\n\n<pre>{tail[:1500]}</pre>"
        )
        sys.exit(1)
    else:
        notify_success(steps_passed, len(STEPS), duration, str(N_TOKENS))
        sys.exit(0)


if __name__ == "__main__":
    main()
