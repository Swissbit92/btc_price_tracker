#!/usr/bin/env bash
# btc-daily.sh — Daily data pipeline (all 17 tokens)
# Runs: spot daily + perp daily + spot weekly + CSV export
# Schedule: 01:05 UTC daily via com.eeva.tracker-daily launchd plist
set -uo pipefail

PROJECT_DIR="/Users/swissbit./nephilim-ecosystem/btc_price_tracker"
cd "${PROJECT_DIR}" || exit 1
VENV="${PROJECT_DIR}/venv/bin/python"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/daily-$(date -u +%Y-%m-%d).log"

# Load environment
set -a
source "${PROJECT_DIR}/.env"
set +a

# Load notification helper
source "${PROJECT_DIR}/bin/notify.sh"

# Ensure logs directory exists
mkdir -p "${LOG_DIR}"

# Rotate old logs (keep 30 days)
find "${LOG_DIR}" -name "daily-*.log" -mtime +30 -delete 2>/dev/null || true

# ── Docker/MongoDB readiness check ──────────────────────────
MAX_WAIT=30
WAITED=0
until docker exec crypto_research_assistant-mongo-1 mongosh --eval "db.adminCommand('ping')" --quiet > /dev/null 2>&1; do
    sleep 2
    WAITED=$((WAITED + 2))
    if [ ${WAITED} -ge ${MAX_WAIT} ]; then
        notify_failure "Daily Update" "🗄 MongoDB not reachable after ${MAX_WAIT}s
🔧 Is Docker running?"
        exit 1
    fi
done

# ── Pipeline steps ──────────────────────────────────────────
STARTED=$(date +%s)
FAILED=""
STEPS_RUN=0
STEPS_PASSED=0

run_step() {
    local name="$1"
    shift
    STEPS_RUN=$((STEPS_RUN + 1))
    echo "" >> "${LOG_FILE}"
    echo "=== Step ${STEPS_RUN}: ${name} — $(date -u +%H:%M:%S) ===" >> "${LOG_FILE}"
    if "${VENV}" "$@" >> "${LOG_FILE}" 2>&1; then
        STEPS_PASSED=$((STEPS_PASSED + 1))
    else
        FAILED="${FAILED}${name}\n"
    fi
}

run_step "Spot daily (17 tokens)" "${PROJECT_DIR}/update.py" --all --timeframe 1d
run_step "Perp daily (17 tokens)" "${PROJECT_DIR}/update.py" --all --timeframe 1d --market-type perp
run_step "Spot weekly (17 tokens)" "${PROJECT_DIR}/update.py" --all --timeframe 1w
run_step "CSV backup"             "${PROJECT_DIR}/export_data.py"

ELAPSED=$(( $(date +%s) - STARTED ))
ELAPSED_MIN=$(( ELAPSED / 60 ))
ELAPSED_SEC=$(( ELAPSED % 60 ))

# ── Report ──────────────────────────────────────────────────
DURATION="${ELAPSED_MIN}m ${ELAPSED_SEC}s"

if [ -n "${FAILED}" ]; then
    TAIL=$(tail -20 "${LOG_FILE}" 2>/dev/null || echo "(no log)")
    notify_failure "Daily Update" "📈 Steps: ${STEPS_PASSED}/${STEPS_RUN} passed
❌ Failed:
$(echo -e "${FAILED}")
⏱ Duration: ${DURATION}

<pre>$(echo "${TAIL}" | head -15)</pre>"
    exit 1
else
    notify_success "Daily Update" "${STEPS_PASSED}" "${STEPS_RUN}" "${DURATION}" "18"
    exit 0
fi
