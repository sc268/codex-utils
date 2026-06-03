# codex-yolo

`codex-yolo` is an Expect wrapper around the Codex CLI. It watches for common approval prompts and answers them automatically.

Defaults:

- edit prompts: `a`, yes and do not ask again for these files
- command-prefix prompts: `p`, yes and do not ask again for this command prefix

Override behavior:

```bash
CODEX_YOLO_EDIT_REPLY=y codex-yolo
CODEX_YOLO_COMMAND_REPLY=y codex-yolo
CODEX_YOLO_REPLY=y codex-yolo
```

Token tracker integration:

```bash
export CODEX_YOLO_STATS_REFRESH=/path/to/codex-utils/token-tracker/refresh-codex-token-usage.command
```

Print usage stats and open the refreshable dashboard:

```bash
codex-yolo --get-usage
```

When installed with `./install.sh`, the token tracker support files are installed with the wrapper. If you use a custom tracker path, set `CODEX_YOLO_STATS_REFRESH` or `CODEX_YOLO_STATS_OPEN`.

Disable stats refresh:

```bash
CODEX_YOLO_SKIP_STATS=1 codex-yolo
```
