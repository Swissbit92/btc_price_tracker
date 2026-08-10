#!/usr/bin/env bash
# Invariant: warmup NaNs must not drop a bar; interior NaNs still block it.
# Exit 1 = violated, 2 = could not determine.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "${REPO}/tools/checks/_lib.sh"
PY="$(resolve_python "${REPO}")"
exec "$PY" -m pytest "${REPO}/tests/test_closed_candles.py::TestNanAnomalies" -q
