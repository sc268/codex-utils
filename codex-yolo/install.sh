#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-/usr/local}"
TARGET="$PREFIX/bin/codex-yolo"

install -m 755 "$SCRIPT_DIR/codex-yolo" "$TARGET"

echo "Installed $TARGET"
echo "For token stats after each run, add this to your shell profile if needed:"
echo "export CODEX_YOLO_STATS_REFRESH=\"$SCRIPT_DIR/../token-tracker/refresh-codex-token-usage.command\""
