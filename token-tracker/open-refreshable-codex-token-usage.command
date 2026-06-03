#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OUTPUT_DIR="${CODEX_TOKEN_USAGE_OUTPUT_DIR:-$HOME/Downloads/codex-token-usage}"
PORT="${CODEX_TOKEN_USAGE_PORT:-8765}"
URL="http://127.0.0.1:${PORT}/index.html"
SERVER_LOG="$OUTPUT_DIR/token-usage-server.log"

"$PYTHON_BIN" -B "$SCRIPT_DIR/codex_token_usage_report.py" --output-dir "$OUTPUT_DIR" >/dev/null

mkdir -p "$OUTPUT_DIR"

if ! curl -fsS "$URL" >/dev/null 2>&1; then
  "$PYTHON_BIN" -B "$SCRIPT_DIR/serve-codex-token-usage.py" \
    --port "$PORT" \
    --directory "$OUTPUT_DIR" \
    --generator "$SCRIPT_DIR/codex_token_usage_report.py" \
    > "$SERVER_LOG" 2>&1 &
  for _ in {1..30}; do
    if curl -fsS "$URL" >/dev/null 2>&1; then
      break
    fi
    sleep 0.2
  done
fi

open "$URL"
