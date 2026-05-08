#!/usr/bin/env bash
# btc-hourly.sh — Hourly data pipeline (all 18 tokens)
# Runs: spot 1h + perp 1h for all tokens
# Schedule: every hour at :05 via com.eeva.tracker-hourly launchd plist
set -uo pipefail

PROJECT_DIR="/Users/swissbit./nephilim/btc_price_tracker"
cd "${PROJECT_DIR}" || exit 1
VENV="${PROJECT_DIR}/venv/bin/python"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/hourly-$(date -u +%Y-%m-%d).log"

# Load environment
set -a
source "${PROJECT_DIR}/.env"
set +a

# Load notification helper
source "${PROJECT_DIR}/bin/notify.sh"

# Ensure logs directory exists
mkdir -p "${LOG_DIR}"

# Rotate old logs (keep 14 days)
find "${LOG_DIR}" -name "hourly-*.log" -mtime +14 -delete 2>/dev/null || true

# ── Docker/MongoDB readiness check ──────────────────────────
MAX_WAIT=30
WAITED=0
until docker exec crypto_research_assistant-mongo-1 mongosh --eval "db.adminCommand('ping')" --quiet > /dev/null 2>&1; do
    sleep 2
    WAITED=$((WAITED + 2))
    if [ ${WAITED} -ge ${MAX_WAIT} ]; then
        notify_failure "Hourly Update (18 tokens)" "🗄 MongoDB not reachable after ${MAX_WAIT}s
🔧 Is Docker running?"
        exit 1
    fi
done

# ── Pipeline steps ──────────────────────────────────────────
FAILED=""

echo "=== Hourly 1h (18 tokens) — $(date -u +%H:%M:%S) ===" >> "${LOG_FILE}"

if ! "${VENV}" "${PROJECT_DIR}/update.py" --all --timeframe 1h >> "${LOG_FILE}" 2>&1; then
    FAILED="${FAILED}spot-1h "
fi

if ! "${VENV}" "${PROJECT_DIR}/update.py" --all --timeframe 1h --market-type perp >> "${LOG_FILE}" 2>&1; then
    FAILED="${FAILED}perp-1h "
fi

# ── Report (failure only — no GREEN for hourly) ─────────────
if [ -n "${FAILED}" ]; then
    TAIL=$(tail -12 "${LOG_FILE}" 2>/dev/null || echo "(no log)")
    notify_failure "Hourly Update (18 tokens)" "🪙 Tokens: 18 (spot + perp 1h)
❌ Failed: ${FAILED}

<pre>$(echo "${TAIL}" | head -10)</pre>"
    exit 1
fi

exit 0
