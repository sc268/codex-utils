#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OUTPUT_DIR="${CODEX_TOKEN_USAGE_OUTPUT_DIR:-$HOME/Downloads/codex-token-usage}"
PORT="${CODEX_TOKEN_USAGE_PORT:-8765}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir|--cache-dir)
      if [[ $# -lt 2 ]]; then
        echo "$1 requires a directory" >&2
        exit 2
      fi
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --port)
      if [[ $# -lt 2 ]]; then
        echo "$1 requires a port" >&2
        exit 2
      fi
      PORT="$2"
      shift 2
      ;;
    *)
      echo "unknown option: $1" >&2
      exit 2
      ;;
  esac
done

URL="http://127.0.0.1:${PORT}/index.html"
SERVER_LOG="$OUTPUT_DIR/token-usage-server.log"
SERVER_PID="$OUTPUT_DIR/token-usage-server.pid"
OPEN_CMD="${CODEX_TOKEN_USAGE_OPEN_CMD:-open}"

CODEX_TOKEN_USAGE_REPORT_URL="$URL" "$SCRIPT_DIR/refresh-codex-token-usage.command" --output-dir "$OUTPUT_DIR"

mkdir -p "$OUTPUT_DIR"

if ! curl -fsS "$URL" >/dev/null 2>&1; then
  "$PYTHON_BIN" -B "$SCRIPT_DIR/serve-codex-token-usage.py" \
    --port "$PORT" \
    --directory "$OUTPUT_DIR" \
    --generator "$SCRIPT_DIR/codex_token_usage_report.py" \
    --daemonize \
    --log-file "$SERVER_LOG" \
    --pid-file "$SERVER_PID"
  for _ in {1..30}; do
    if curl -fsS "$URL" >/dev/null 2>&1; then
      break
    fi
    sleep 0.2
  done
fi

if ! curl -fsS "$URL" >/dev/null 2>&1; then
  echo "codex token usage server did not start at $URL; see $SERVER_LOG" >&2
  exit 1
fi

"$OPEN_CMD" "$URL"
