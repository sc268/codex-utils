#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -z "${PREFIX:-}" ]]; then
  if [[ "$(uname -s)" == "Darwin" ]]; then
    PREFIX="/usr/local"
  else
    PREFIX="${HOME:-/usr/local}/.local"
  fi
fi

BIN_DIR="$PREFIX/bin"
SHARE_DIR="$PREFIX/share/codex-utils"
TARGET="$BIN_DIR/codex-yolo"

install -d "$BIN_DIR" "$SHARE_DIR/codex-yolo" "$SHARE_DIR/token-tracker"
install -m 755 "$SCRIPT_DIR/codex-yolo" "$SHARE_DIR/codex-yolo/codex-yolo"
install -m 755 "$SCRIPT_DIR/codex-yolo.expect" "$SHARE_DIR/codex-yolo/codex-yolo.expect"
install -m 755 "$SCRIPT_DIR/codex-yolo.pexpect" "$SHARE_DIR/codex-yolo/codex-yolo.pexpect"
install -m 755 "$REPO_DIR/token-tracker/codex_token_usage_report.py" "$SHARE_DIR/token-tracker/codex_token_usage_report.py"
install -m 755 "$REPO_DIR/token-tracker/serve-codex-token-usage.py" "$SHARE_DIR/token-tracker/serve-codex-token-usage.py"
install -m 755 "$REPO_DIR/token-tracker/refresh-codex-token-usage.command" "$SHARE_DIR/token-tracker/refresh-codex-token-usage.command"
install -m 755 "$REPO_DIR/token-tracker/open-refreshable-codex-token-usage.command" "$SHARE_DIR/token-tracker/open-refreshable-codex-token-usage.command"

cat > "$TARGET" <<EOF
#!/bin/bash
set -euo pipefail

CODEX_UTILS_SHARE_DIR="$SHARE_DIR"

export CODEX_YOLO_STATS_REFRESH="\${CODEX_YOLO_STATS_REFRESH:-\$CODEX_UTILS_SHARE_DIR/token-tracker/refresh-codex-token-usage.command}"
export CODEX_YOLO_STATS_OPEN="\${CODEX_YOLO_STATS_OPEN:-\$CODEX_UTILS_SHARE_DIR/token-tracker/open-refreshable-codex-token-usage.command}"

exec "\$CODEX_UTILS_SHARE_DIR/codex-yolo/codex-yolo" "\$@"
EOF

chmod 755 "$TARGET"

echo "Installed $TARGET"
echo "Installed support files in $SHARE_DIR"
echo "Run codex-yolo --get-usage to print usage stats and open the dashboard."

case ":${PATH:-}:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Add $BIN_DIR to PATH before running codex-yolo." ;;
esac
