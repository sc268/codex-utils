#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OUTPUT_DIR="${CODEX_TOKEN_USAGE_OUTPUT_DIR:-$HOME/Downloads/codex-token-usage}"

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
    *)
      echo "unknown option: $1" >&2
      exit 2
      ;;
  esac
done

REPORT_JSON="$OUTPUT_DIR/codex-token-usage.json"
REPORT_HTML="$OUTPUT_DIR/index.html"
REPORT_URL="${CODEX_TOKEN_USAGE_REPORT_URL:-file://$REPORT_HTML}"

"$PYTHON_BIN" -B "$SCRIPT_DIR/codex_token_usage_report.py" --output-dir "$OUTPUT_DIR" >/dev/null

summary="$("$PYTHON_BIN" - "$REPORT_JSON" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    report = json.load(handle)

summary = report.get("summary", {})
totals = summary.get("totals", {})

def n(value):
    try:
        return f"{int(value):,}"
    except Exception:
        return "0"

print(
    f"{n(totals.get('total_tokens'))} total tokens "
    f"({n(totals.get('input_tokens'))} input, "
    f"{n(totals.get('cached_input_tokens'))} cached, "
    f"{n(totals.get('output_tokens'))} output, "
    f"{n(totals.get('reasoning_output_tokens'))} reasoning) "
    f"across {n(summary.get('tracked_session_count'))}/{n(summary.get('session_count'))} sessions"
)
PY
)"

printf 'codex stats updates w %s, check %s\n' "$summary" "$REPORT_URL"
