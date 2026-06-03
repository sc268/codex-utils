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

Install `codex-yolo` into `/usr/local/bin`:

```bash
./codex-yolo/install.sh
```

If `codex-yolo` cannot find the sibling token tracker after installation, set:

```bash
export CODEX_YOLO_STATS_REFRESH=/path/to/codex-utils/token-tracker/refresh-codex-token-usage.command
```

Set `CODEX_YOLO_SKIP_STATS=1` to skip token report refresh after a `codex-yolo` run.
