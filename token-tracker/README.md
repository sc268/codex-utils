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
```

Use a custom output directory:

```bash
./codex_token_usage_report.py --output-dir /path/to/output
```

or:

```bash
export CODEX_TOKEN_USAGE_OUTPUT_DIR=/path/to/output
```

The static `file://` HTML cannot run local scripts. Use `open-refreshable-codex-token-usage.command` if you want the `Refresh Logs` button inside the page to update the report.
