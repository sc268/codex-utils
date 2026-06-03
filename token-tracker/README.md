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
- `machines/<machine-id>.json`

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

Shared cloud folders are supported. Run the refresh command on each computer with the same `--output-dir`; each computer updates its own `machines/<machine-id>.json` snapshot, and the top-level report aggregates all snapshots.

Use a custom output directory:

```bash
./codex_token_usage_report.py --output-dir /path/to/output
```

or:

```bash
export CODEX_TOKEN_USAGE_OUTPUT_DIR=/path/to/output
```

Use a custom computer label:

```bash
./refresh-codex-token-usage.command --output-dir /path/to/output --machine-name "Work Laptop"
```

Use `--machine-id` or `CODEX_TOKEN_USAGE_MACHINE_ID` if two computers have the same hostname.

Use a custom browser opener command:

```bash
export CODEX_TOKEN_USAGE_OPEN_CMD=/path/to/open-command
```

The static `file://` HTML cannot run local scripts. Use `open-refreshable-codex-token-usage.command` if you want the `Refresh Logs` button inside the page to update the report.
