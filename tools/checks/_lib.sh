#!/usr/bin/env bash
# Shared interpreter resolution for invariant checks.
#
# Exit codes matter here: 1 means the invariant is VIOLATED, 2 means we could
# not determine it. Falling back to an interpreter that cannot import the
# project's dependencies would report a violation that is really a broken
# environment — a check that fails for the wrong reason is as bad as one that
# passes for the wrong reason, so resolve_python exits 2 instead.
#
# Override with PYTHON=/path/to/python (used when running from a git worktree,
# which has no venv of its own).

resolve_python() {
  local repo="$1" py=""

  if [ -n "${PYTHON:-}" ] && [ -x "${PYTHON}" ]; then
    py="${PYTHON}"
  elif [ -x "${repo}/venv/bin/python" ]; then
    py="${repo}/venv/bin/python"
  elif [ -x "${repo}/.venv/bin/python" ]; then
    py="${repo}/.venv/bin/python"
  else
    py="$(command -v python3 || true)"
  fi

  if [ -z "${py}" ]; then
    echo "UNDETERMINED: no python3 found" >&2
    exit 2
  fi
  if ! "${py}" -c "import pandas, pytest" 2>/dev/null; then
    echo "UNDETERMINED: ${py} cannot import pandas/pytest — this is an environment" >&2
    echo "problem, not an invariant violation. Set PYTHON= or create the repo venv." >&2
    exit 2
  fi

  printf '%s' "${py}"
}
