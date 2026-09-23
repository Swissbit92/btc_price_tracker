#!/usr/bin/env bash
# Invariant: every Telegram alert goes through btc_tracker_mongodb/alerting.py,
# which retries transient failures. Exit 1 = violated, 2 = could not determine.
#
# The three launchd entrypoints each carried their own `_send_telegram`, and all
# three ended in `except Exception: pass`. These are the FAILURE alerts — the
# message that says the pipeline broke — so the case where the send fails is
# exactly the case where something has already gone wrong and nobody is told.
#
# Two of the three never looked at the HTTP response, only at whether an
# exception was raised, so a 400 returned True: a failure rendered as a success,
# which is this ecosystem's most-repeated defect.
#
# See docs/INVARIANTS.md. Sibling rules, same week: eeva-exec INV-10, eeva-dca
# INV-1, nephilim-ecosystem INV-2. The repos never import each other, so the RULE
# travels and the implementation does not.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "${REPO}/tools/checks/_lib.sh"
PY="$(resolve_python "${REPO}")"

SENDER="${REPO}/btc_tracker_mongodb/alerting.py"
if [[ ! -f "${SENDER}" ]]; then
  echo "COULD NOT DETERMINE: ${SENDER} is missing — this check has lost its" >&2
  echo "subject. Re-point it rather than deleting it." >&2
  exit 2
fi

# A funnel that no longer separates retryable from permanent is a loop, not a
# policy. Both must survive for the check below to mean anything.
for required in RETRY_STATUSES SEND_ATTEMPTS "def send_alert"; do
  if ! grep -q "${required}" "${SENDER}"; then
    echo "COULD NOT DETERMINE: ${SENDER} no longer defines '${required}' —" >&2
    echo "the retry policy has been hollowed out." >&2
    exit 2
  fi
done

# 1. The behaviour, including the case no grep can see: an upload must be
#    REBUILT per attempt, or a retry uploads an empty body and calls it success.
"$PY" -m pytest "${REPO}/tests/test_alerting.py" -q

# 2. The structure: nothing outside the shared sender may build a Telegram
#    request of its own.
offenders="$(grep -rln 'api\.telegram\.org' \
  --include='*.py' \
  "${REPO}/bin" "${REPO}/btc_tracker_mongodb" "${REPO}/tools" 2>/dev/null \
  | grep -v 'btc_tracker_mongodb/alerting.py' || true)"

if [[ -n "${offenders}" ]]; then
  echo "VIOLATION: these build a Telegram request directly instead of using" >&2
  echo "btc_tracker_mongodb.alerting.send_alert, so one dropped connection" >&2
  echo "loses the alert outright:" >&2
  echo "${offenders}" >&2
  exit 1
fi

# 3. Zero guarded sites is a broken query, not a pass.
guarded="$(grep -rl 'from btc_tracker_mongodb.alerting import' --include='*.py' "${REPO}/bin" 2>/dev/null | wc -l | tr -d ' ')"
if [[ "${guarded}" -eq 0 ]]; then
  echo "COULD NOT DETERMINE: no entrypoint imports the shared sender. That is a" >&2
  echo "moved notifier, not a clean repo." >&2
  exit 2
fi

echo "INVARIANT holds: ${guarded} entrypoint(s) send through alerting.send_alert."
