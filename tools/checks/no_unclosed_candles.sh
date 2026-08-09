#!/usr/bin/env bash
# Invariant: never write a candle whose period has not closed.
# Exit 1 = violated, 2 = could not determine.
#
# Storing an in-progress bar freezes it — the next run's gap check sees the
# timestamp as present and never revisits it. See docs/LESSONS_LEARNED.md
# (2026-07-19).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "${REPO}/tools/checks/_lib.sh"
PY="$(resolve_python "${REPO}")"
exec "$PY" -m pytest "${REPO}/tests/test_closed_candles.py" -q
