# codex-utils

Small local utilities for Codex CLI users.

## Tools

- `codex-yolo/`: a Codex CLI launcher that uses Codex's native approval/sandbox bypass option and integrates token usage reporting.
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

Run Codex through the YOLO launcher from the repo checkout:

```bash
./codex-yolo/codex-yolo
```

Print usage stats and open the refreshable token dashboard:

```bash
./codex-yolo/codex-yolo --get-usage
```

Show supported wrapper commands and options:

```bash
./codex-yolo/codex-yolo -h
```

Use a specific report folder without setting an environment variable:

```bash
./codex-yolo/codex-yolo --get-usage --output-dir /path/to/output
./codex-yolo/codex-yolo --update-cache-dir /path/to/output
```

For a shared cloud folder, run the same command on each computer. Each computer writes `machines/<machine-id>.json`; `index.html` aggregates all machine snapshots and shows both per-computer and total usage.

The dashboard includes active-day average usage, per-computer totals, token usage by project folder, daily charts, sortable session rows, computer/project/model/min-token filters, search, and filtered JSON export.

Customize the computer label:

```bash
./codex-yolo/codex-yolo --update-cache-dir /path/to/output --machine-name "Work Laptop"
```

Use `--machine-id` if two computers have the same hostname.

Install `codex-yolo` into `/usr/local/bin`:

```bash
./codex-yolo/install.sh
```

The installer also copies the token tracker support files into:

```bash
/usr/local/share/codex-utils
```

Override `PREFIX=/some/path` to install somewhere else. `codex-yolo --get-usage` uses the installed open script automatically. Set `CODEX_YOLO_STATS_OPEN` only if the open script lives somewhere else.

Normal `codex-yolo` runs refresh token stats in the background after Codex exits, so the shell prompt is not blocked by report generation. Set `CODEX_YOLO_STATS_MODE=sync` for blocking refresh, `CODEX_YOLO_STATS_MODE=off` to disable it, or `CODEX_YOLO_SKIP_STATS=1` to skip token report refresh after a run.
