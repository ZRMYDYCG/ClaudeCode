#!/usr/bin/env bash
# Format the file Cursor just edited (afterFileEdit).
# Fail open: never block the agent if formatting fails.
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 0

input="$(cat)"
file_path="$(printf '%s' "$input" | jq -r '.file_path // empty')"

if [[ -z "$file_path" || ! -f "$file_path" ]]; then
  exit 0
fi

# Only touch Python sources in this repo.
case "$file_path" in
  *.py) ;;
  *) exit 0 ;;
esac

# Prefer project venv ruff; fall back to uv run.
if [[ -x "$ROOT/.venv/bin/ruff" ]]; then
  RUFF=("$ROOT/.venv/bin/ruff")
elif command -v uv >/dev/null 2>&1; then
  RUFF=(uv run ruff)
else
  exit 0
fi

"${RUFF[@]}" format --quiet "$file_path" >/dev/null 2>&1 || true
"${RUFF[@]}" check --fix --quiet "$file_path" >/dev/null 2>&1 || true

exit 0
