#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

if [[ -f "$PROJECT_DIR/.env" ]]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
elif [[ -x "$PROJECT_DIR/../asti-demo/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_DIR/../asti-demo/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" -m engine.gt_corpus --days 21 --max-articles 250 --workers 8
"$PYTHON_BIN" -m engine.prompt_research --days 21 --per-topic 4
set +e
"$PYTHON_BIN" -m engine.real_collector collect
COLLECT_EXIT=$?
set -e
if [[ "$COLLECT_EXIT" -gt 1 ]]; then
  exit "$COLLECT_EXIT"
fi
if [[ "$COLLECT_EXIT" -eq 1 ]]; then
  echo "Warning: collection completed with prompt-level errors; continuing with audit and assessment."
fi
"$PYTHON_BIN" -m engine.content_audit --latest --workers 10
exec "$PYTHON_BIN" -m engine.deep_assessment --media "Global Times"
