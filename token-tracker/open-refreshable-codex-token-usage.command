#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OUTPUT_DIR="${CODEX_TOKEN_USAGE_OUTPUT_DIR:-$HOME/Downloads/codex-token-usage}"
PORT="${CODEX_TOKEN_USAGE_PORT:-8765}"
GENERATOR_ARGS=()

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
    --machine-name|--machine-id)
      if [[ $# -lt 2 ]]; then
        echo "$1 requires a value" >&2
        exit 2
      fi
      GENERATOR_ARGS+=("$1" "$2")
      shift 2
      ;;
    *)
      echo "unknown option: $1" >&2
      exit 2
      ;;
  esac
done

OUTPUT_DIR="$("$PYTHON_BIN" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve())' "$OUTPUT_DIR")"

port_serves_output_dir() {
  local check_port="$1"
  curl -fsS "http://127.0.0.1:${check_port}/codex-token-usage.json" 2>/dev/null | "$PYTHON_BIN" -c '
import json
import sys
from pathlib import Path

expected = Path(sys.argv[1]).expanduser().resolve()
try:
    metadata = json.load(sys.stdin).get("metadata", {})
    snapshot_dir = metadata.get("snapshot_dir")
    actual = Path(snapshot_dir).expanduser().resolve().parent if snapshot_dir else None
except Exception:
    actual = None
raise SystemExit(0 if actual == expected else 1)
' "$OUTPUT_DIR"
}

for _ in {1..50}; do
  if ! curl -fsS "http://127.0.0.1:${PORT}/index.html" >/dev/null 2>&1; then
    break
  fi
  if port_serves_output_dir "$PORT"; then
    break
  fi
  PORT=$((PORT + 1))
done

URL="http://127.0.0.1:${PORT}/index.html"
SERVER_LOG="$OUTPUT_DIR/token-usage-server.log"
SERVER_PID="$OUTPUT_DIR/token-usage-server.pid"

if [[ -n "${CODEX_TOKEN_USAGE_OPEN_CMD:-}" ]]; then
  OPEN_CMD="$CODEX_TOKEN_USAGE_OPEN_CMD"
elif command -v xdg-open >/dev/null 2>&1; then
  OPEN_CMD="xdg-open"
elif command -v open >/dev/null 2>&1; then
  OPEN_CMD="open"
else
  OPEN_CMD=""
fi

if [[ ${#GENERATOR_ARGS[@]} -gt 0 ]]; then
  CODEX_TOKEN_USAGE_REPORT_URL="$URL" "$SCRIPT_DIR/refresh-codex-token-usage.command" --output-dir "$OUTPUT_DIR" "${GENERATOR_ARGS[@]}"
else
  CODEX_TOKEN_USAGE_REPORT_URL="$URL" "$SCRIPT_DIR/refresh-codex-token-usage.command" --output-dir "$OUTPUT_DIR"
fi

mkdir -p "$OUTPUT_DIR"

if ! curl -fsS "$URL" >/dev/null 2>&1; then
  if [[ ${#GENERATOR_ARGS[@]} -gt 0 ]]; then
    "$PYTHON_BIN" -B "$SCRIPT_DIR/serve-codex-token-usage.py" \
      --port "$PORT" \
      --directory "$OUTPUT_DIR" \
      --generator "$SCRIPT_DIR/codex_token_usage_report.py" \
      "${GENERATOR_ARGS[@]}" \
      --daemonize \
      --log-file "$SERVER_LOG" \
      --pid-file "$SERVER_PID"
  else
    "$PYTHON_BIN" -B "$SCRIPT_DIR/serve-codex-token-usage.py" \
      --port "$PORT" \
      --directory "$OUTPUT_DIR" \
      --generator "$SCRIPT_DIR/codex_token_usage_report.py" \
      --daemonize \
      --log-file "$SERVER_LOG" \
      --pid-file "$SERVER_PID"
  fi
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

if [[ -n "$OPEN_CMD" ]]; then
  if ! "$OPEN_CMD" "$URL"; then
    echo "codex token usage dashboard is available at $URL" >&2
  fi
else
  echo "codex token usage dashboard is available at $URL" >&2
fi
