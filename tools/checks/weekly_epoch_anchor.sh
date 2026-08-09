#!/usr/bin/env bash
# Invariant: weekly candle boundaries are epoch-anchored (ts % 604800 == 0),
# never weekday-anchored. Exit 1 = violated, 2 = could not determine.
#
# Hardcoding Monday here stalled every weekly update for three weeks in 2026.
# See docs/INVARIANTS.md and docs/LESSONS_LEARNED.md (2026-08-09).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "${REPO}/tools/checks/_lib.sh"
PY="$(resolve_python "${REPO}")"
exec "$PY" -m pytest "${REPO}/tests/test_closed_candles.py" -q \
  -k "epoch_aligned or exchange_anchor_not_the_iso_week or not_stalled_by_the_anchor"
