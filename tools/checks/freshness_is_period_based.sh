#!/usr/bin/env bash
# Invariant: freshness is measured in whole periods behind the last closed
# period, never as wall-clock age. Exit 1 = violated, 2 = could not determine.
#
# A wall-clock threshold is correct only at the hour the job happens to run:
# at 21:28 UTC the old 36h daily bound reported 34 healthy collections stale.
# See docs/INVARIANTS.md and docs/LESSONS_LEARNED.md (2026-08-09).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "${REPO}/tools/checks/_lib.sh"
PY="$(resolve_python "${REPO}")"

# 1. The behaviour: periods_behind must be hour-invariant.
"$PY" -m pytest "${REPO}/tests/test_closed_candles.py::TestPeriodsBehind" -q

# 2. The structure: the watchdog must not reintroduce a wall-clock comparison
#    for OHLCV. `now - latest` survives only in the funding branch, which is a
#    documented exception.
if grep -nE '^\s*age\s*=\s*now\s*-\s*latest' "${REPO}/bin/run_watchdog.py" | wc -l | grep -qv '^ *1$'; then
  echo "VIOLATION: bin/run_watchdog.py has more than the one permitted" >&2
  echo "wall-clock age comparison (the funding exception)." >&2
  exit 1
fi
