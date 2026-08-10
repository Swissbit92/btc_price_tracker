#!/usr/bin/env bash
# Invariant: compute_all never raises, whatever the series length.
# Exit 1 = violated, 2 = could not determine.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "${REPO}/tools/checks/_lib.sh"
PY="$(resolve_python "${REPO}")"
exec "$PY" -m pytest "${REPO}/tests/test_indicators_short_history.py" -q
