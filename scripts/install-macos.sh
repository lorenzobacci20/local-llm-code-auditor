#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python_is_compatible() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

resolve_python() {
  local candidate resolved

  if [[ -n "${LOCAL_LLM_CODE_AUDITOR_PYTHON:-}" ]]; then
    if [[ -x "$LOCAL_LLM_CODE_AUDITOR_PYTHON" ]] && python_is_compatible "$LOCAL_LLM_CODE_AUDITOR_PYTHON"; then
      printf '%s\n' "$LOCAL_LLM_CODE_AUDITOR_PYTHON"
      return 0
    fi
  fi

  for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    resolved="$(command -v "$candidate" 2>/dev/null || true)"
    [[ -n "$resolved" ]] || continue

    if python_is_compatible "$resolved"; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done

  return 1
}

PYTHON_BIN="$(resolve_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Error: Local LLM Code Auditor requires Python >= 3.11." >&2
  echo "Install Python 3.11+ or set LOCAL_LLM_CODE_AUDITOR_PYTHON=/path/to/python." >&2
  exit 1
fi

echo "Using $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"

if [[ -x .venv/bin/python ]] && ! python_is_compatible .venv/bin/python; then
  echo "Existing .venv uses an incompatible Python; recreating it..."
  rm -rf .venv
fi

if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
[[ -f agent.toml ]] || cp agent.example.toml agent.toml

echo "Installed. Edit agent.toml, then run: .venv/bin/local-llm-code-auditor --config agent.toml"
