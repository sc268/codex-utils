# claude-yolo

`claude-yolo` is a Claude Code CLI launcher for uninterrupted local runs that
also restores web access when you use a custom `ANTHROPIC_BASE_URL`.

It does two things:

1. Runs the Claude Code CLI with `--dangerously-skip-permissions`.
2. Registers a local MCP server that adds `web_search` and `web_fetch` tools.

## Why the web MCP server

Claude Code's built-in `WebSearch` / `WebFetch` tools execute **server-side on
Anthropic's infrastructure**. When `ANTHROPIC_BASE_URL` points at a gateway or
proxy, those server-side tools are not available, so Claude loses web access.

The bundled MCP server (`web-mcp-server.py`) runs **locally on your machine** and
hits the network directly, so it works regardless of the base URL. It needs **no
paid web search API key**:

- `web_search` uses DuckDuckGo's free HTML endpoint.
- `web_fetch` does a plain HTTP GET and converts HTML to readable text.

It is pure Python standard library — no third-party dependencies.

## Usage

From the repo checkout:

```bash
./claude-yolo/claude-yolo
```

Arguments are passed straight through to the Claude CLI:

```bash
./claude-yolo/claude-yolo --model sonnet -p "search the web for X"
```

Once running, Claude can call the `web_search` and `web_fetch` tools (exposed by
the `web` MCP server). With `--dangerously-skip-permissions` they run without
prompting.

Show wrapper help:

```bash
./claude-yolo/claude-yolo -h
```

## Environment

```bash
CLAUDE_YOLO_CLAUDE_BIN=/path/to/claude   # Claude CLI binary (default: claude)
CLAUDE_YOLO_PYTHON_BIN=python3           # Python for the MCP server
CLAUDE_YOLO_WEB_MCP=/path/to/server.py   # Override the bundled MCP server path
CLAUDE_YOLO_WEB=0                        # Do not register the web MCP server
CLAUDE_YOLO_SKIP_PERMISSIONS=0           # Do not pass --dangerously-skip-permissions
```

For example, to launch with skipped permissions but no web tools:

```bash
CLAUDE_YOLO_WEB=0 ./claude-yolo/claude-yolo
```

Or to add web tools but keep normal permission prompts:

```bash
CLAUDE_YOLO_SKIP_PERMISSIONS=0 ./claude-yolo/claude-yolo
```

## Install

```bash
./claude-yolo/install.sh
```

On Linux the default prefix is `~/.local`; on macOS it is `/usr/local`. Override
with `PREFIX=/some/path ./claude-yolo/install.sh`. The installer copies the MCP
server alongside the wrapper so the installed `claude-yolo` finds it.

## Testing the MCP server directly

The server speaks newline-delimited JSON-RPC over stdin/stdout:

```bash
printf '%s\n%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"web_search","arguments":{"query":"hello world"}}}' \
  | python3 claude-yolo/web-mcp-server.py
```
