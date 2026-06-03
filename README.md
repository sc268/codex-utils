# codex-utils

Small local utilities for Codex CLI users.

## Tools

- `codex-yolo/`: an Expect wrapper that runs `codex` interactively and auto-accepts common approval prompts.
- `token-tracker/`: a local token usage reporter that scans `~/.codex/sessions` and generates an offline HTML dashboard, CSV, and JSON.

## Token Tracker Output

By default, token reports are written to:

```bash
~/Downloads/codex-token-usage
```

That default is intentional: generated reports stay out of the git checkout, and users can find the HTML easily. Override it with either:

```bash
./token-tracker/codex_token_usage_report.py --output-dir /path/to/output
```

or:

```bash
export CODEX_TOKEN_USAGE_OUTPUT_DIR=/path/to/output
```

## Quick Start

Generate a report without opening a browser:

```bash
./token-tracker/refresh-codex-token-usage.command
```

Open a localhost dashboard where the in-page `Refresh Logs` button works:

```bash
./token-tracker/open-refreshable-codex-token-usage.command
```

Run Codex through the approval helper from the repo checkout:

```bash
./codex-yolo/codex-yolo
```

Print usage stats and open the refreshable token dashboard:

```bash
./codex-yolo/codex-yolo --get-usage
```

Install `codex-yolo` into `/usr/local/bin`:

```bash
./codex-yolo/install.sh
```

The installer also copies the token tracker support files into:

```bash
/usr/local/share/codex-utils
```

Override `PREFIX=/some/path` to install somewhere else. `codex-yolo --get-usage` uses the installed open script automatically. Set `CODEX_YOLO_STATS_OPEN` only if the open script lives somewhere else.

Set `CODEX_YOLO_SKIP_STATS=1` to skip token report refresh after a `codex-yolo` run.
