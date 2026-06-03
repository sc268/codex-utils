# token-tracker

Generate a local Codex token usage report from Codex session logs.

Input:

```bash
~/.codex/sessions
```

Default output:

```bash
~/Downloads/codex-token-usage
```

Generated files:

- `index.html`
- `codex-token-usage.csv`
- `codex-token-usage.json`

Generate or refresh the report:

```bash
./refresh-codex-token-usage.command
```

Open the localhost report with an in-page refresh button:

```bash
./open-refreshable-codex-token-usage.command
./open-refreshable-codex-token-usage.command --output-dir /path/to/output
```

That command also prints the latest aggregate usage stats.

Use a custom output directory:

```bash
./codex_token_usage_report.py --output-dir /path/to/output
```

or:

```bash
export CODEX_TOKEN_USAGE_OUTPUT_DIR=/path/to/output
```

Use a custom browser opener command:

```bash
export CODEX_TOKEN_USAGE_OPEN_CMD=/path/to/open-command
```

The static `file://` HTML cannot run local scripts. Use `open-refreshable-codex-token-usage.command` if you want the `Refresh Logs` button inside the page to update the report.
