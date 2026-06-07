#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ -z "${PREFIX:-}" ]]; then
  if [[ "$(uname -s)" == "Darwin" ]]; then
    PREFIX="/usr/local"
  else
    PREFIX="${HOME:-/usr/local}/.local"
  fi
fi

BIN_DIR="$PREFIX/bin"
SHARE_DIR="$PREFIX/share/codex-utils/claude-yolo"
TARGET="$BIN_DIR/claude-yolo"

# mkdir -p (not `install -d`) so we don't try to re-chmod pre-existing,
# possibly root-owned directories like /usr/local/bin.
mkdir -p "$BIN_DIR" "$SHARE_DIR"
install -m 755 "$SCRIPT_DIR/claude-yolo" "$SHARE_DIR/claude-yolo"
install -m 755 "$SCRIPT_DIR/web-mcp-server.py" "$SHARE_DIR/web-mcp-server.py"

cat > "$TARGET" <<EOF
#!/bin/bash
set -euo pipefail

CLAUDE_YOLO_SHARE_DIR="$SHARE_DIR"

export CLAUDE_YOLO_WEB_MCP="\${CLAUDE_YOLO_WEB_MCP:-\$CLAUDE_YOLO_SHARE_DIR/web-mcp-server.py}"

exec "\$CLAUDE_YOLO_SHARE_DIR/claude-yolo" "\$@"
EOF

chmod 755 "$TARGET"

echo "Installed $TARGET"
echo "Installed support files in $SHARE_DIR"
echo "Run claude-yolo to launch Claude with skipped permissions and web tools."

case ":${PATH:-}:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Add $BIN_DIR to PATH before running claude-yolo." ;;
esac
