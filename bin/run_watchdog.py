#!/usr/bin/env python3
"""
run_watchdog.py — MongoDB data freshness watchdog.

Independent alarm layer: launchd runs this daily, and it fires a RED Telegram
alert if any token's data is stale — regardless of whether the writer scripts
(run_daily.py, run_hourly.py) ran, crashed, or were silently killed by launchd
before Python started. On Sundays it also sends a GREEN heartbeat so absence
of the green signal is itself a failure indicator for the watchdog itself.

Schedule: 07:00 local via com.eeva.tracker-watchdog launchd plist.
"""

import os
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

from dotenv import load_dotenv
load_dotenv(PROJECT_DIR / ".env")

LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"watchdog-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"
HEADER_IMAGE = PROJECT_DIR / "images" / "PriceTracker_01.png"
HOSTNAME = os.uname().nodename.split(".")[0]

# Thresholds: allow for one missed run + clock skew.
# Daily/perp-daily: 36h (next run at T+24h, plus 12h grace).
# 1h/perp-1h: 3h (latest candle is typically 1-2h old since current hour is forming).
# Weekly: skipped — pre-existing inconsistency (SOL/PEPE/ARB stale at 04-02) unrelated to watchdog's purpose.
THRESHOLDS = {
    ("1d", "spot"): timedelta(hours=36),
    ("1d", "perp"): timedelta(hours=36),
    ("1h", "spot"): timedelta(hours=3),
    ("1h", "perp"): timedelta(hours=3),
}


def _send_telegram(msg, photo_path=None):
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        return False
    import requests
    try:
        if photo_path and Path(photo_path).is_file():
            with open(photo_path, "rb") as f:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": msg[:1024], "parse_mode": "HTML"},
                    files={"photo": f}, timeout=20,
                )
        else:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
                timeout=20,
            )
        return True
    except Exception:
        return False


def notify_stale(stale_rows, checked):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = "\n".join(f"  \u2022 {r}" for r in stale_rows[:30])
    if len(stale_rows) > 30:
        body += f"\n  \u2026 and {len(stale_rows) - 30} more"
    msg = (
        f"\U0001f6a8 Data Freshness Alert \U0001f6a8\n\n"
        f"\u23f0 {ts}\n"
        f"\U0001f5a5 {HOSTNAME}\n\n"
        f"\u274c Stale collections: {len(stale_rows)}/{checked}\n\n"
        f"<pre>{body}</pre>\n\n"
        f"\U0001f527 Check writer launchd jobs + MongoDB\n"
        f"\U0001f525 #Crypto #Eeva #Watchdog"
    )
    photo = str(HEADER_IMAGE) if HEADER_IMAGE.is_file() else None
    _send_telegram(msg, photo)


def notify_heartbeat(checked):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = (
        f"\U0001f49a Watchdog Heartbeat \U0001f49a\n\n"
        f"\u23f0 {ts}\n"
        f"\U0001f5a5 {HOSTNAME}\n\n"
        f"\u2705 All {checked} collections fresh\n"
        f"\U0001f4ca Freshness watchdog alive\n"
        f"\U0001f525 #Crypto #Eeva #Watchdog"
    )
    photo = str(HEADER_IMAGE) if HEADER_IMAGE.is_file() else None
    _send_telegram(msg, photo)


def notify_watchdog_error(detail):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = (
        f"\U0001f6a8 Watchdog Self-Error \U0001f6a8\n\n"
        f"\u23f0 {ts}\n"
        f"\U0001f5a5 {HOSTNAME}\n\n"
        f"\u274c Watchdog itself failed to complete:\n"
        f"<pre>{detail[:1500]}</pre>\n"
        f"\U0001f525 #Crypto #Eeva #Watchdog"
    )
    _send_telegram(msg)


def check_freshness(log):
    from btc_tracker_mongodb.config import TOKENS
    from btc_tracker_mongodb.db import get_collection

    now = datetime.now(timezone.utc)
    stale, checked = [], 0

    for symbol in TOKENS:
        for (tf, mt), threshold in THRESHOLDS.items():
            checked += 1
            try:
                c = get_collection(symbol, tf, market_type=mt)
                doc = c.find_one(sort=[("timestamp", -1)])
                if doc is None:
                    stale.append(f"{symbol} {tf} {mt}: EMPTY")
                    continue
                latest = doc["timestamp"]
                if latest.tzinfo is None:
                    latest = latest.replace(tzinfo=timezone.utc)
                age = now - latest
                if age > threshold:
                    stale.append(
                        f"{symbol} {tf} {mt}: {latest.strftime('%Y-%m-%d %H:%M')} "
                        f"({int(age.total_seconds() / 3600)}h old, threshold {int(threshold.total_seconds() / 3600)}h)"
                    )
            except Exception as e:
                stale.append(f"{symbol} {tf} {mt}: QUERY ERROR {type(e).__name__}")

    log.write(f"Checked {checked} collections — {len(stale)} stale\n")
    for s in stale:
        log.write(f"  STALE: {s}\n")
    log.flush()
    return stale, checked


def main():
    with open(LOG_FILE, "a") as log:
        run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        log.write(f"\n===== Watchdog run {run_ts} UTC =====\n")
        log.flush()

        try:
            stale, checked = check_freshness(log)
        except Exception:
            tb = traceback.format_exc()
            log.write(f"FATAL: {tb}\n")
            log.flush()
            notify_watchdog_error(tb)
            sys.exit(2)

        if stale:
            notify_stale(stale, checked)
            log.write(f"Sent RED alert: {len(stale)} stale\n")
            sys.exit(1)

        # Sunday weekly heartbeat (weekday() == 6) — proves watchdog itself is alive.
        if datetime.now(timezone.utc).weekday() == 6:
            notify_heartbeat(checked)
            log.write(f"Sent GREEN heartbeat (Sunday)\n")

        log.write(f"OK: all {checked} collections fresh\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
