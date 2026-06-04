# codex-yolo

`codex-yolo` is a Codex CLI launcher that uses Expect to auto-answer common approval prompts.

Defaults:

- command prompts such as `Would you like to run the following command?`: `p`, yes and do not ask again for matching command prefixes
- edit prompts such as `Would you like to make the following edits?`: `a`, yes and do not ask again for these files

Use a different Codex binary:

```bash
CODEX_YOLO_CODEX_BIN=/path/to/codex codex-yolo
```

Override the approval defaults:

```bash
CODEX_YOLO_COMMAND_REPLY=y codex-yolo
CODEX_YOLO_EDIT_REPLY=y codex-yolo
CODEX_YOLO_REPLY=y codex-yolo
```

Show supported commands and options:

```bash
codex-yolo -h
```

Token tracker integration:

```bash
export CODEX_YOLO_STATS_REFRESH=/path/to/codex-utils/token-tracker/refresh-codex-token-usage.command
```

Print usage stats and open the refreshable dashboard:

```bash
codex-yolo --get-usage
```

Use a specific report folder without setting `CODEX_TOKEN_USAGE_OUTPUT_DIR`:

```bash
codex-yolo --get-usage --output-dir /path/to/output
codex-yolo --update-cache-dir /path/to/output
```

When multiple computers use the same cloud output folder, each one writes a snapshot under `machines/`. The generated `index.html` totals every snapshot and includes a per-computer breakdown.

The dashboard also includes active-day averages, project-folder usage, daily charts, filters, sortable rows, and filtered JSON export.

Customize the computer label:

```bash
codex-yolo --update-cache-dir /path/to/output --machine-name "Work Laptop"
```

When installed with `./install.sh`, the token tracker support files are installed with the wrapper. If you use a custom tracker path, set `CODEX_YOLO_STATS_REFRESH` or `CODEX_YOLO_STATS_OPEN`.

Disable stats refresh:

```bash
CODEX_YOLO_SKIP_STATS=1 codex-yolo
```

Normal runs refresh token stats in the background after Codex exits. Use the old blocking behavior only when needed:

```bash
CODEX_YOLO_STATS_MODE=sync codex-yolo
```
