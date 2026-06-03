#!/usr/bin/env python3
"""
Generate a local Codex token usage report from ~/.codex session logs.

The Codex CLI writes JSONL session files under ~/.codex/sessions. Recent
versions include event_msg records whose payload type is token_count. This
script reads those records and writes an offline HTML dashboard, CSV, and JSON.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import socket
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def empty_usage() -> dict[str, int]:
    return {key: 0 for key in USAGE_KEYS}


def add_usage(target: dict[str, int], source: dict[str, int]) -> None:
    for key in USAGE_KEYS:
        target[key] += int(source.get(key, 0) or 0)


def normalize_usage(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None

    result = empty_usage()
    found = False
    for key in USAGE_KEYS:
        raw = value.get(key)
        if raw is None:
            continue
        try:
            result[key] = int(raw)
            found = True
        except (TypeError, ValueError):
            continue

    if not found:
        return None

    if result["total_tokens"] == 0:
        result["total_tokens"] = result["input_tokens"] + result["output_tokens"]

    return result


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def ensure_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def to_local(value: datetime | None) -> datetime | None:
    value = ensure_aware(value)
    if value is None:
        return None
    return value.astimezone()


def iso_or_empty(value: datetime | None) -> str:
    value = ensure_aware(value)
    return value.isoformat() if value else ""


def local_display(value: datetime | None) -> str:
    local_value = to_local(value)
    if local_value is None:
        return ""
    return local_value.strftime("%Y-%m-%d %H:%M:%S %Z")


def local_date(value: datetime | None) -> str:
    local_value = to_local(value)
    if local_value is None:
        return "unknown"
    return local_value.strftime("%Y-%m-%d")


def clean_text(value: Any, max_len: int = 180) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) > max_len:
        return f"{text[: max_len - 3]}..."
    return text


def slugify(value: str, fallback: str = "machine") -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip(".-_")
    return slug[:80] or fallback


def default_machine_name() -> str:
    configured = os.environ.get("CODEX_TOKEN_USAGE_MACHINE_NAME") or os.environ.get("CODEX_TOKEN_USAGE_MACHINE")
    if configured:
        return configured
    return socket.gethostname() or "machine"


def project_name_from_path(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text == "unknown":
        return "unknown"
    name = Path(text).name
    return name or text


def content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    pieces: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            pieces.append(text)
    return "\n".join(pieces)


def is_environment_context(value: str) -> bool:
    return value.lstrip().startswith("<environment_context>")


def fallback_timestamp_from_mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def parse_session_file(path: Path, codex_home: Path) -> dict[str, Any]:
    started_at: datetime | None = None
    ended_at: datetime | None = None
    latest_total_usage: dict[str, int] | None = None
    summed_last_usage = empty_usage()

    record: dict[str, Any] = {
        "session_id": path.stem.replace("rollout-", ""),
        "session_file": str(path),
        "relative_file": str(path),
        "cwd": "",
        "model": "",
        "model_provider": "",
        "cli_version": "",
        "originator": "",
        "source": "",
        "first_user_message": "",
        "user_messages": 0,
        "token_events_seen": 0,
        "usage_events": 0,
        "turns_with_usage": 0,
        "invalid_json_lines": 0,
        "model_context_window": None,
    }

    try:
        record["relative_file"] = str(path.relative_to(codex_home))
    except ValueError:
        record["relative_file"] = str(path)

    try:
        handle = path.open("r", encoding="utf-8", errors="replace")
    except OSError as exc:
        record["read_error"] = str(exc)
        return finalize_record(record, started_at, ended_at, latest_total_usage, summed_last_usage, path)

    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                record["invalid_json_lines"] += 1
                continue

            event_time = parse_timestamp(event.get("timestamp"))
            if event_time is not None:
                started_at = event_time if started_at is None or event_time < started_at else started_at
                ended_at = event_time if ended_at is None or event_time > ended_at else ended_at

            event_type = event.get("type")
            payload = event.get("payload")
            if not isinstance(payload, dict):
                payload = {}

            if event_type == "session_meta":
                meta_time = parse_timestamp(payload.get("timestamp"))
                if meta_time is not None:
                    started_at = meta_time if started_at is None or meta_time < started_at else started_at
                record["session_id"] = str(payload.get("id") or record["session_id"])
                record["cwd"] = str(payload.get("cwd") or record["cwd"])
                record["model_provider"] = str(payload.get("model_provider") or record["model_provider"])
                record["cli_version"] = str(payload.get("cli_version") or record["cli_version"])
                record["originator"] = str(payload.get("originator") or record["originator"])
                record["source"] = str(payload.get("source") or record["source"])

            elif event_type == "turn_context":
                record["cwd"] = str(payload.get("cwd") or record["cwd"])
                record["model"] = str(payload.get("model") or record["model"])

            elif event_type == "event_msg":
                payload_type = payload.get("type")

                if payload_type == "user_message":
                    message = clean_text(payload.get("message"))
                    if message:
                        record["user_messages"] += 1
                        if not record["first_user_message"] or is_environment_context(record["first_user_message"]):
                            record["first_user_message"] = message

                elif payload_type == "token_count":
                    record["token_events_seen"] += 1
                    info = payload.get("info")
                    if not isinstance(info, dict):
                        continue

                    context_window = info.get("model_context_window")
                    if context_window is not None:
                        try:
                            record["model_context_window"] = int(context_window)
                        except (TypeError, ValueError):
                            pass

                    total_usage = normalize_usage(info.get("total_token_usage"))
                    last_usage = normalize_usage(info.get("last_token_usage"))
                    if total_usage is not None:
                        latest_total_usage = total_usage
                        record["usage_events"] += 1
                    if last_usage is not None:
                        add_usage(summed_last_usage, last_usage)
                        if last_usage["total_tokens"] > 0:
                            record["turns_with_usage"] += 1

            elif event_type == "response_item":
                if payload.get("type") == "message" and payload.get("role") == "user":
                    message = clean_text(content_text(payload.get("content")))
                    if message and not is_environment_context(message) and not record["first_user_message"]:
                        record["first_user_message"] = message

    return finalize_record(record, started_at, ended_at, latest_total_usage, summed_last_usage, path)


def finalize_record(
    record: dict[str, Any],
    started_at: datetime | None,
    ended_at: datetime | None,
    latest_total_usage: dict[str, int] | None,
    summed_last_usage: dict[str, int],
    path: Path,
) -> dict[str, Any]:
    if started_at is None:
        started_at = fallback_timestamp_from_mtime(path)
    if ended_at is None:
        ended_at = started_at

    usage = latest_total_usage or summed_last_usage
    has_usage = bool(usage and usage.get("total_tokens", 0) > 0)
    if usage is None:
        usage = empty_usage()

    duration_minutes = 0.0
    aware_start = ensure_aware(started_at)
    aware_end = ensure_aware(ended_at)
    if aware_start is not None and aware_end is not None:
        duration_minutes = max(0.0, (aware_end - aware_start).total_seconds() / 60.0)

    record.update(
        {
            "started_at": iso_or_empty(started_at),
            "started_local": local_display(started_at),
            "ended_at": iso_or_empty(ended_at),
            "ended_local": local_display(ended_at),
            "date": local_date(started_at),
            "duration_minutes": round(duration_minutes, 1),
            "has_usage": has_usage,
            "status": "tracked" if has_usage else "no token_count found",
            "summed_last_usage": summed_last_usage,
        }
    )
    record.update(usage)
    return record


def iter_session_files(codex_home: Path) -> list[Path]:
    sessions_dir = codex_home / "sessions"
    if not sessions_dir.exists():
        return []
    files: list[Path] = []
    for pattern in ("**/*.jsonl", "**/*.json"):
        files.extend(path for path in sessions_dir.glob(pattern) if path.is_file())
    return sorted(set(files))


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    tracked = [record for record in records if record.get("has_usage")]
    totals = empty_usage()
    by_day: dict[str, dict[str, int]] = defaultdict(empty_usage)
    by_model: dict[str, dict[str, int]] = defaultdict(empty_usage)
    by_cwd: dict[str, dict[str, int]] = defaultdict(empty_usage)
    by_project: dict[str, dict[str, Any]] = {}
    by_machine: dict[str, dict[str, Any]] = {}

    for record in records:
        machine_id = str(record.get("machine_id") or "unknown")
        machine_name = str(record.get("machine_name") or machine_id or "unknown")
        if machine_id not in by_machine:
            by_machine[machine_id] = {
                "machine_id": machine_id,
                "name": machine_name,
                "session_count": 0,
                "tracked_session_count": 0,
                "untracked_session_count": 0,
                **empty_usage(),
            }
        by_machine[machine_id]["session_count"] += 1
        if record.get("has_usage"):
            by_machine[machine_id]["tracked_session_count"] += 1
        else:
            by_machine[machine_id]["untracked_session_count"] += 1

    for record in tracked:
        usage = {key: int(record.get(key, 0) or 0) for key in USAGE_KEYS}
        add_usage(totals, usage)
        add_usage(by_day[str(record.get("date") or "unknown")], usage)
        model = str(record.get("model") or "unknown")
        cwd = str(record.get("cwd") or "unknown")
        add_usage(by_model[model], usage)
        add_usage(by_cwd[cwd], usage)
        if cwd not in by_project:
            by_project[cwd] = {
                "name": project_name_from_path(cwd),
                "path": cwd,
                "session_count": 0,
                "tracked_session_count": 0,
                **empty_usage(),
            }
        by_project[cwd]["session_count"] += 1
        by_project[cwd]["tracked_session_count"] += 1
        add_usage(by_project[cwd], usage)
        machine_id = str(record.get("machine_id") or "unknown")
        if machine_id in by_machine:
            add_usage(by_machine[machine_id], usage)

    def sorted_usage(mapping: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
        return [
            {"name": name, **usage}
            for name, usage in sorted(
                mapping.items(),
                key=lambda item: (item[1].get("total_tokens", 0), item[0]),
                reverse=True,
            )
        ]

    top_sessions = sorted(tracked, key=lambda item: int(item.get("total_tokens", 0) or 0), reverse=True)[:20]

    daily = [{"name": name, **usage} for name, usage in sorted(by_day.items(), key=lambda item: item[0])]
    active_daily = [day for day in daily if int(day.get("total_tokens", 0) or 0) > 0]
    active_day_count = len(active_daily)
    avg_daily = empty_usage()
    if active_day_count:
        for key in USAGE_KEYS:
            avg_daily[key] = round(sum(int(day.get(key, 0) or 0) for day in active_daily) / active_day_count)
    machines = sorted(
        by_machine.values(),
        key=lambda item: (int(item.get("total_tokens", 0) or 0), str(item.get("name") or "")),
        reverse=True,
    )
    projects = sorted(
        by_project.values(),
        key=lambda item: (int(item.get("total_tokens", 0) or 0), str(item.get("path") or "")),
        reverse=True,
    )
    for project in projects:
        sessions = int(project.get("tracked_session_count", 0) or 0)
        project["avg_tokens_per_session"] = round(int(project.get("total_tokens", 0) or 0) / sessions) if sessions else 0

    return {
        "session_count": len(records),
        "tracked_session_count": len(tracked),
        "untracked_session_count": len(records) - len(tracked),
        "machine_count": len(machines),
        "active_day_count": active_day_count,
        "avg_daily": avg_daily,
        "totals": totals,
        "daily": daily,
        "machines": machines,
        "models": sorted_usage(by_model),
        "projects": projects,
        "workdirs": sorted_usage(by_cwd)[:25],
        "top_sessions": top_sessions,
    }


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "date",
        "started_local",
        "ended_local",
        "duration_minutes",
        "machine_name",
        "machine_id",
        "session_id",
        "status",
        "total_tokens",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "turns_with_usage",
        "model",
        "cwd",
        "first_user_message",
        "session_file",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})


def html_report(report: dict[str, Any]) -> str:
    report_json = json.dumps(report, ensure_ascii=True, separators=(",", ":")).replace("</", "<\\/")
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex Token Usage</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #667085;
      --line: #d9dee7;
      --input: #2f80ed;
      --cached: #16a085;
      --output: #b54708;
      --reasoning: #7c3aed;
      --accent: #111827;
      --shadow: 0 1px 2px rgba(16, 24, 40, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      padding: 28px 32px 18px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }
    h1 {
      margin: 0 0 8px;
      font-size: 28px;
      line-height: 1.15;
      letter-spacing: 0;
    }
    .meta {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      overflow-wrap: anywhere;
    }
    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
    }
    .actions {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 6px;
      min-width: 190px;
    }
    button {
      border: 1px solid #111827;
      border-radius: 6px;
      background: #111827;
      color: #ffffff;
      font: inherit;
      font-weight: 700;
      padding: 9px 12px;
      cursor: pointer;
      white-space: nowrap;
    }
    button:disabled {
      cursor: default;
      opacity: 0.62;
    }
    .status-text {
      min-height: 18px;
      color: var(--muted);
      font-size: 12px;
      text-align: right;
      line-height: 1.4;
    }
    main {
      padding: 24px 32px 36px;
      display: grid;
      gap: 18px;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(6, minmax(130px, 1fr));
      gap: 12px;
    }
    .metric, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .metric {
      padding: 14px 16px;
      min-height: 88px;
    }
    .metric .label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .06em;
    }
    .metric .value {
      margin-top: 8px;
      font-size: 24px;
      font-weight: 700;
      line-height: 1.1;
      overflow-wrap: anywhere;
    }
    .metric .sub {
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
    }
    .panel {
      padding: 16px;
      min-width: 0;
    }
    .panel h2 {
      margin: 0;
      font-size: 16px;
      line-height: 1.3;
    }
    .section-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      color: var(--muted);
      font-size: 12px;
    }
    .legend span {
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .swatch {
      width: 10px;
      height: 10px;
      border-radius: 2px;
      display: inline-block;
    }
    .charts {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(320px, .8fr);
      gap: 18px;
    }
    .daily-total-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(300px, .34fr);
      gap: 18px;
      align-items: start;
    }
    .chart-box {
      width: 100%;
      overflow-x: auto;
    }
    svg {
      display: block;
      max-width: 100%;
      height: auto;
      font-family: inherit;
    }
    .controls {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }
    input[type="search"] {
      width: min(460px, 100%);
      padding: 9px 11px;
      border: 1px solid var(--line);
      border-radius: 6px;
      font: inherit;
      background: #ffffff;
    }
    input[type="number"], select {
      width: 100%;
      padding: 9px 11px;
      border: 1px solid var(--line);
      border-radius: 6px;
      font: inherit;
      background: #ffffff;
    }
    button.secondary {
      background: #ffffff;
      color: #111827;
    }
    .filters {
      display: grid;
      grid-template-columns: repeat(5, minmax(150px, 1fr));
      gap: 12px;
      align-items: end;
    }
    .filter-field {
      display: grid;
      gap: 6px;
    }
    .filter-field label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    .filter-actions {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .project-grid {
      display: grid;
      grid-template-columns: minmax(0, .9fr) minmax(420px, 1.1fr);
      gap: 18px;
      align-items: start;
    }
    .computer-grid {
      display: grid;
      grid-template-columns: minmax(0, .8fr) minmax(420px, 1.2fr);
      gap: 18px;
      align-items: start;
    }
    .links {
      display: flex;
      gap: 10px;
      white-space: nowrap;
    }
    a {
      color: #175cd3;
      text-decoration: none;
      font-weight: 600;
    }
    a:hover { text-decoration: underline; }
    .table-wrap {
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    table {
      width: 100%;
      min-width: 1180px;
      border-collapse: collapse;
      background: #ffffff;
      font-size: 13px;
    }
    .daily-table {
      min-width: 460px;
    }
    .machine-table {
      min-width: 760px;
    }
    .project-table {
      min-width: 760px;
    }
    .daily-table th {
      cursor: default;
    }
    .daily-total-wrap {
      max-height: 300px;
      overflow: auto;
    }
    th, td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    th {
      position: sticky;
      top: 0;
      background: #f9fafb;
      color: #344054;
      font-weight: 700;
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
    }
    tr:last-child td { border-bottom: 0; }
    td.num {
      text-align: right;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    td.path, td.prompt {
      max-width: 360px;
      overflow-wrap: anywhere;
      color: #344054;
    }
    .pill {
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      background: #eef4ff;
      color: #175cd3;
      white-space: nowrap;
    }
    .pill.empty {
      background: #f2f4f7;
      color: #667085;
    }
    .empty-state {
      color: var(--muted);
      padding: 20px 0;
    }
    @media (max-width: 980px) {
      header, main { padding-left: 16px; padding-right: 16px; }
      .topbar { flex-direction: column; }
      .actions { align-items: flex-start; }
      .status-text { text-align: left; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .charts { grid-template-columns: 1fr; }
      .daily-total-grid { grid-template-columns: 1fr; }
      .filters { grid-template-columns: 1fr; }
      .project-grid { grid-template-columns: 1fr; }
      .computer-grid { grid-template-columns: 1fr; }
      .controls { align-items: stretch; flex-direction: column; }
      .links { justify-content: flex-start; }
    }
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <div>
        <h1>Codex Token Usage</h1>
        <div class="meta" id="meta"></div>
      </div>
      <div class="actions">
        <button id="refreshButton" type="button">Refresh Logs</button>
        <div class="status-text" id="refreshStatus"></div>
      </div>
    </div>
  </header>
  <main>
    <section class="metrics" id="metrics"></section>

    <section class="panel">
      <div class="section-head">
        <h2>Data Explorer</h2>
        <div class="legend" id="filterSummary"></div>
      </div>
      <div class="filters">
        <div class="filter-field">
          <label for="machineFilter">Computer</label>
          <select id="machineFilter"></select>
        </div>
        <div class="filter-field">
          <label for="projectFilter">Project Folder</label>
          <select id="projectFilter"></select>
        </div>
        <div class="filter-field">
          <label for="modelFilter">Model</label>
          <select id="modelFilter"></select>
        </div>
        <div class="filter-field">
          <label for="minTokensFilter">Min Tokens</label>
          <input id="minTokensFilter" type="number" min="0" step="1000" placeholder="0">
        </div>
        <div class="filter-actions">
          <button id="resetFilters" class="secondary" type="button">Reset</button>
          <button id="exportFiltered" class="secondary" type="button">Export JSON</button>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-head">
        <h2>Computer Breakdown</h2>
      </div>
      <div class="computer-grid">
        <div class="chart-box" id="machineChart"></div>
        <div class="table-wrap">
          <table class="machine-table">
            <thead>
              <tr>
                <th>Computer</th>
                <th>Total</th>
                <th>Input</th>
                <th>Cached</th>
                <th>Output</th>
                <th>Reasoning</th>
                <th>Sessions</th>
              </tr>
            </thead>
            <tbody id="machineBody"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-head">
        <h2>Project Folder Usage</h2>
        <div class="legend">
          <span><i class="swatch" style="background: var(--input)"></i>Input</span>
          <span><i class="swatch" style="background: var(--output)"></i>Output</span>
        </div>
      </div>
      <div class="project-grid">
        <div class="chart-box" id="projectChart"></div>
        <div class="table-wrap">
          <table class="project-table">
            <thead>
              <tr>
                <th>Project</th>
                <th>Total</th>
                <th>Avg / Session</th>
                <th>Sessions</th>
              </tr>
            </thead>
            <tbody id="projectBody"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-head">
        <h2>Total Daily Usage</h2>
        <div class="legend">
          <span><i class="swatch" style="background: var(--accent)"></i>Total tokens</span>
        </div>
      </div>
      <div class="daily-total-grid">
        <div class="chart-box" id="dailyTotalChart"></div>
        <div class="table-wrap daily-total-wrap">
          <table class="daily-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Total</th>
                <th>Sessions</th>
              </tr>
            </thead>
            <tbody id="dailyTotalsBody"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="charts">
      <div class="panel">
        <div class="section-head">
          <h2>Daily Breakdown</h2>
          <div class="legend">
            <span><i class="swatch" style="background: var(--input)"></i>Input</span>
            <span><i class="swatch" style="background: var(--output)"></i>Output</span>
            <span><i class="swatch" style="background: var(--reasoning)"></i>Reasoning subset</span>
          </div>
        </div>
        <div class="chart-box" id="dailyChart"></div>
      </div>
      <div class="panel">
        <div class="section-head">
          <h2>Largest Sessions</h2>
        </div>
        <div class="chart-box" id="topChart"></div>
      </div>
    </section>

    <section class="panel">
      <div class="controls">
        <input id="search" type="search" placeholder="Filter table by machine, model, folder, session id, or first message">
        <div class="links">
          <a href="codex-token-usage.csv">CSV</a>
          <a href="codex-token-usage.json">JSON</a>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th data-key="started_at">Start</th>
              <th data-key="total_tokens">Total</th>
              <th data-key="input_tokens">Input</th>
              <th data-key="cached_input_tokens">Cached</th>
              <th data-key="output_tokens">Output</th>
              <th data-key="reasoning_output_tokens">Reasoning</th>
              <th data-key="turns_with_usage">Turns</th>
              <th data-key="machine_name">Machine</th>
              <th data-key="model">Model</th>
              <th data-key="cwd">Folder</th>
              <th data-key="first_user_message">First Message</th>
              <th data-key="status">Status</th>
            </tr>
          </thead>
          <tbody id="tableBody"></tbody>
        </table>
      </div>
    </section>
  </main>

  <script>
    const report = __REPORT_JSON__;
    const records = report.records || [];
    const summary = report.summary || {};
    let sortKey = "started_at";
    let sortDir = -1;
    let dashboardRows = records.slice();
    let dashboardSummary = summary;

    const fmt = new Intl.NumberFormat();
    const colors = {
      input: "#2f80ed",
      output: "#b54708",
      reasoning: "#7c3aed",
      muted: "#667085",
      line: "#d9dee7",
      total: "#111827"
    };

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[char]));
    }

    function number(value) {
      return fmt.format(Number(value || 0));
    }

    function metric(label, value, sub) {
      return `<div class="metric"><div class="label">${label}</div><div class="value">${value}</div><div class="sub">${sub || ""}</div></div>`;
    }

    function projectName(path) {
      const text = String(path || "unknown");
      const pieces = text.split("/").filter(Boolean);
      return pieces[pieces.length - 1] || text;
    }

    function usageFrom(row) {
      return {
        input_tokens: Number(row.input_tokens || 0),
        cached_input_tokens: Number(row.cached_input_tokens || 0),
        output_tokens: Number(row.output_tokens || 0),
        reasoning_output_tokens: Number(row.reasoning_output_tokens || 0),
        total_tokens: Number(row.total_tokens || 0)
      };
    }

    function addUsage(target, usage) {
      Object.keys(usage).forEach(key => {
        target[key] = Number(target[key] || 0) + Number(usage[key] || 0);
      });
    }

    function emptyUsage() {
      return {
        input_tokens: 0,
        cached_input_tokens: 0,
        output_tokens: 0,
        reasoning_output_tokens: 0,
        total_tokens: 0
      };
    }

    function sortUsageRows(rows) {
      return rows.sort((a, b) => Number(b.total_tokens || 0) - Number(a.total_tokens || 0) || String(a.name || a.path || "").localeCompare(String(b.name || b.path || "")));
    }

    function aggregateRows(rows) {
      const tracked = rows.filter(row => row.has_usage);
      const totals = emptyUsage();
      const byDay = new Map();
      const byMachine = new Map();
      const byProject = new Map();
      const byModel = new Map();

      rows.forEach(row => {
        const machineId = row.machine_id || "unknown";
        const machineName = row.machine_name || machineId;
        if (!byMachine.has(machineId)) {
          byMachine.set(machineId, { machine_id: machineId, name: machineName, session_count: 0, tracked_session_count: 0, untracked_session_count: 0, ...emptyUsage() });
        }
        const machine = byMachine.get(machineId);
        machine.session_count += 1;
        if (row.has_usage) {
          machine.tracked_session_count += 1;
        } else {
          machine.untracked_session_count += 1;
        }
      });

      tracked.forEach(row => {
        const usage = usageFrom(row);
        addUsage(totals, usage);

        const date = row.date || "unknown";
        if (!byDay.has(date)) byDay.set(date, { name: date, ...emptyUsage() });
        addUsage(byDay.get(date), usage);

        const machineId = row.machine_id || "unknown";
        if (byMachine.has(machineId)) addUsage(byMachine.get(machineId), usage);

        const path = row.cwd || "unknown";
        if (!byProject.has(path)) {
          byProject.set(path, { name: projectName(path), path, session_count: 0, tracked_session_count: 0, ...emptyUsage() });
        }
        const project = byProject.get(path);
        project.session_count += 1;
        project.tracked_session_count += 1;
        addUsage(project, usage);

        const model = row.model || "unknown";
        if (!byModel.has(model)) byModel.set(model, { name: model, ...emptyUsage() });
        addUsage(byModel.get(model), usage);
      });

      const daily = Array.from(byDay.values()).sort((a, b) => String(a.name).localeCompare(String(b.name)));
      const activeDaily = daily.filter(day => Number(day.total_tokens || 0) > 0);
      const avgDaily = emptyUsage();
      if (activeDaily.length) {
        Object.keys(avgDaily).forEach(key => {
          avgDaily[key] = Math.round(activeDaily.reduce((sum, day) => sum + Number(day[key] || 0), 0) / activeDaily.length);
        });
      }

      const projects = sortUsageRows(Array.from(byProject.values())).map(project => ({
        ...project,
        avg_tokens_per_session: project.tracked_session_count ? Math.round(Number(project.total_tokens || 0) / project.tracked_session_count) : 0
      }));

      return {
        session_count: rows.length,
        tracked_session_count: tracked.length,
        untracked_session_count: rows.length - tracked.length,
        machine_count: byMachine.size,
        active_day_count: activeDaily.length,
        avg_daily: avgDaily,
        totals,
        daily,
        machines: sortUsageRows(Array.from(byMachine.values())),
        projects,
        models: sortUsageRows(Array.from(byModel.values())),
        top_sessions: tracked.slice().sort((a, b) => Number(b.total_tokens || 0) - Number(a.total_tokens || 0)).slice(0, 20)
      };
    }

    function renderMeta() {
      const generated = report.metadata.generated_local || report.metadata.generated_at || "";
      const snapshotDir = report.metadata.snapshot_dir || "";
      const source = snapshotDir ? `${number(summary.machine_count || 0)} computer snapshots in ${snapshotDir}` : (report.metadata.codex_sessions_dir || "");
      document.getElementById("meta").textContent = `Generated ${generated}. Source: ${source}`;
    }

    function wireRefreshButton() {
      const button = document.getElementById("refreshButton");
      const status = document.getElementById("refreshStatus");
      const isLocalServer = location.protocol === "http:" && /^127\\.0\\.0\\.1$|^localhost$/.test(location.hostname);

      if (!isLocalServer) {
        status.textContent = "Open with open-refreshable-codex-token-usage.command to enable this button.";
        button.addEventListener("click", () => {
          status.textContent = "file:// pages cannot run local scripts. Start the localhost report first.";
        });
        return;
      }

      status.textContent = "Ready";
      button.addEventListener("click", async () => {
        button.disabled = true;
        status.textContent = "Scanning Codex logs...";
        try {
          const response = await fetch("/refresh", { method: "POST" });
          const payload = await response.json();
          if (!response.ok || !payload.ok) {
            throw new Error(payload.error || `HTTP ${response.status}`);
          }
          status.textContent = "Updated. Reloading...";
          window.location.reload();
        } catch (error) {
          status.textContent = `Refresh failed: ${error.message || error}`;
          button.disabled = false;
        }
      });
    }

    function selected(id) {
      const element = document.getElementById(id);
      return element ? element.value : "";
    }

    function option(value, label) {
      return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
    }

    function uniqueOptions(rows, getter) {
      return Array.from(new Set(rows.map(getter).filter(Boolean))).sort((a, b) => String(a).localeCompare(String(b)));
    }

    function populateFilters() {
      const machine = document.getElementById("machineFilter");
      const project = document.getElementById("projectFilter");
      const model = document.getElementById("modelFilter");
      machine.innerHTML = option("", "All computers") + uniqueOptions(records, row => row.machine_name || row.machine_id || "unknown").map(value => option(value, value)).join("");
      project.innerHTML = option("", "All folders") + uniqueOptions(records, row => row.cwd || "unknown").map(value => option(value, value)).join("");
      model.innerHTML = option("", "All models") + uniqueOptions(records, row => row.model || "unknown").map(value => option(value, value)).join("");
    }

    function explorerRows() {
      const machine = selected("machineFilter");
      const project = selected("projectFilter");
      const model = selected("modelFilter");
      const minTokens = Number(selected("minTokensFilter") || 0);
      return records.filter(row => {
        if (machine && (row.machine_name || row.machine_id || "unknown") !== machine) return false;
        if (project && (row.cwd || "unknown") !== project) return false;
        if (model && (row.model || "unknown") !== model) return false;
        if (minTokens && Number(row.total_tokens || 0) < minTokens) return false;
        return true;
      });
    }

    function renderFilterSummary(rows, current) {
      document.getElementById("filterSummary").innerHTML = [
        `<span>${number(rows.length)} sessions</span>`,
        `<span>${number(current.tracked_session_count || 0)} tracked</span>`,
        `<span>${number(current.active_day_count || 0)} active days</span>`
      ].join("");
    }

    function wireFilters() {
      ["machineFilter", "projectFilter", "modelFilter", "minTokensFilter"].forEach(id => {
        document.getElementById(id).addEventListener("input", renderDashboard);
      });
      document.getElementById("resetFilters").addEventListener("click", () => {
        ["machineFilter", "projectFilter", "modelFilter", "minTokensFilter", "search"].forEach(id => {
          const element = document.getElementById(id);
          if (element) element.value = "";
        });
        renderDashboard();
      });
      document.getElementById("exportFiltered").addEventListener("click", () => {
        const payload = {
          metadata: {
            generated_at: new Date().toISOString(),
            source_report_generated_at: report.metadata.generated_at || "",
            filtered_session_count: dashboardRows.length
          },
          summary: dashboardSummary,
          records: filteredRows()
        };
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "codex-token-usage-filtered.json";
        link.click();
        URL.revokeObjectURL(url);
      });
    }

    function renderMetrics() {
      const totals = dashboardSummary.totals || {};
      const avgDaily = dashboardSummary.avg_daily || {};
      const tracked = dashboardSummary.tracked_session_count || 0;
      const all = dashboardSummary.session_count || 0;
      document.getElementById("metrics").innerHTML = [
        metric("Total Tokens", number(totals.total_tokens), `${number(tracked)} tracked sessions`),
        metric("Avg Active Day", number(avgDaily.total_tokens), `${number(dashboardSummary.active_day_count || 0)} non-zero days`),
        metric("Input", number(totals.input_tokens), `${number(totals.cached_input_tokens)} cached`),
        metric("Output", number(totals.output_tokens), "Visible plus reasoning output"),
        metric("Reasoning", number(totals.reasoning_output_tokens), "Subset of output tokens"),
        metric("Computers", number(dashboardSummary.machine_count || 0), `${number((dashboardSummary.projects || []).length)} project folders`)
      ].join("");
    }

    function renderMachineChart() {
      const data = dashboardSummary.machines || [];
      const target = document.getElementById("machineChart");
      if (!data.length) {
        target.innerHTML = '<div class="empty-state">No computer usage found.</div>';
        return;
      }
      const width = 620;
      const rowH = 34;
      const height = data.length * rowH + 18;
      const labelW = 150;
      const barW = width - labelW - 92;
      const maxTotal = Math.max(...data.map(item => Number(item.total_tokens || 0)), 1);
      const rows = data.map((item, i) => {
        const y = 10 + i * rowH;
        const w = barW * Number(item.total_tokens || 0) / maxTotal;
        const label = item.name || item.machine_id || "unknown";
        return `
          <g>
            <title>${escapeHtml(label)}: ${number(item.total_tokens)} tokens</title>
            <text x="0" y="${y + 15}" font-size="12" fill="${colors.muted}">${escapeHtml(String(label).slice(0, 22))}</text>
            <rect x="${labelW}" y="${y}" width="${barW}" height="18" fill="#eef2f7" rx="4"></rect>
            ${stackedBar(labelW, y, w, 18, Number(item.input_tokens || 0), Number(item.output_tokens || 0), Math.max(Number(item.input_tokens || 0) + Number(item.output_tokens || 0), 1))}
            <text x="${labelW + barW + 8}" y="${y + 14}" font-size="12" fill="${colors.muted}">${number(item.total_tokens)}</text>
          </g>
        `;
      }).join("");
      target.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Per-computer token usage chart">${rows}</svg>`;
    }

    function renderMachineTable() {
      const data = dashboardSummary.machines || [];
      const body = document.getElementById("machineBody");
      if (!data.length) {
        body.innerHTML = '<tr><td colspan="7">No computer usage found.</td></tr>';
        return;
      }
      body.innerHTML = data.map(machine => `
        <tr>
          <td>${escapeHtml(machine.name || machine.machine_id || "unknown")}</td>
          <td class="num">${number(machine.total_tokens)}</td>
          <td class="num">${number(machine.input_tokens)}</td>
          <td class="num">${number(machine.cached_input_tokens)}</td>
          <td class="num">${number(machine.output_tokens)}</td>
          <td class="num">${number(machine.reasoning_output_tokens)}</td>
          <td class="num">${number(machine.tracked_session_count || 0)} / ${number(machine.session_count || 0)}</td>
        </tr>
      `).join("");
    }

    function renderProjectChart() {
      const data = (dashboardSummary.projects || []).slice(0, 12);
      const target = document.getElementById("projectChart");
      if (!data.length) {
        target.innerHTML = '<div class="empty-state">No project folder usage found.</div>';
        return;
      }
      const width = 760;
      const rowH = 36;
      const height = data.length * rowH + 18;
      const labelW = 230;
      const barW = width - labelW - 110;
      const maxTotal = Math.max(...data.map(item => Number(item.total_tokens || 0)), 1);
      const rows = data.map((item, i) => {
        const y = 10 + i * rowH;
        const w = barW * Number(item.total_tokens || 0) / maxTotal;
        const label = item.name || item.path || "unknown";
        return `
          <g>
            <title>${escapeHtml(item.path || label)}: ${number(item.total_tokens)} tokens</title>
            <text x="0" y="${y + 15}" font-size="12" fill="${colors.muted}">${escapeHtml(String(label).slice(0, 30))}</text>
            <rect x="${labelW}" y="${y}" width="${barW}" height="18" fill="#eef2f7" rx="4"></rect>
            ${stackedBar(labelW, y, w, 18, Number(item.input_tokens || 0), Number(item.output_tokens || 0), Math.max(Number(item.input_tokens || 0) + Number(item.output_tokens || 0), 1))}
            <text x="${labelW + barW + 8}" y="${y + 14}" font-size="12" fill="${colors.muted}">${number(item.total_tokens)}</text>
          </g>
        `;
      }).join("");
      target.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Project folder token usage chart">${rows}</svg>`;
    }

    function renderProjectTable() {
      const data = (dashboardSummary.projects || []).slice(0, 30);
      const body = document.getElementById("projectBody");
      if (!data.length) {
        body.innerHTML = '<tr><td colspan="4">No project folder usage found.</td></tr>';
        return;
      }
      body.innerHTML = data.map(project => `
        <tr>
          <td class="path" title="${escapeHtml(project.path || "")}">${escapeHtml(project.name || project.path || "unknown")}</td>
          <td class="num">${number(project.total_tokens)}</td>
          <td class="num">${number(project.avg_tokens_per_session)}</td>
          <td class="num">${number(project.tracked_session_count || 0)}</td>
        </tr>
      `).join("");
    }

    function sessionsForDate(date) {
      return dashboardRows.filter(row => row.has_usage && row.date === date).length;
    }

    function renderDailyTotalChart() {
      const data = dashboardSummary.daily || [];
      const target = document.getElementById("dailyTotalChart");
      if (!data.length) {
        target.innerHTML = '<div class="empty-state">No token usage records found.</div>';
        return;
      }

      const width = Math.max(780, data.length * 54);
      const height = 310;
      const pad = { top: 22, right: 28, bottom: 62, left: 78 };
      const chartW = width - pad.left - pad.right;
      const chartH = height - pad.top - pad.bottom;
      const maxTotal = Math.max(...data.map(d => Number(d.total_tokens || 0)), 1);
      const barW = Math.max(16, Math.min(36, chartW / data.length * 0.64));
      const gap = chartW / data.length;
      const ticks = [0, 0.25, 0.5, 0.75, 1];

      const grid = ticks.map(tick => {
        const y = pad.top + chartH - chartH * tick;
        return `
          <line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" stroke="${colors.line}"></line>
          <text x="12" y="${y + 4}" font-size="12" fill="${colors.muted}">${number(Math.round(maxTotal * tick))}</text>
        `;
      }).join("");

      const bars = data.map((d, i) => {
        const total = Number(d.total_tokens || 0);
        const h = chartH * total / maxTotal;
        const x = pad.left + i * gap + (gap - barW) / 2;
        const y = pad.top + chartH - h;
        const sessionCount = sessionsForDate(d.name);
        return `
          <g>
            <title>${escapeHtml(d.name)}: ${number(total)} total tokens across ${number(sessionCount)} sessions</title>
            <rect x="${x}" y="${y}" width="${barW}" height="${h}" fill="${colors.total}" rx="4"></rect>
            <text x="${x + barW / 2}" y="${height - 30}" text-anchor="end" transform="rotate(-45 ${x + barW / 2} ${height - 30})" font-size="11" fill="${colors.muted}">${escapeHtml(d.name)}</text>
          </g>
        `;
      }).join("");

      target.innerHTML = `
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Total daily token usage chart">
          ${grid}
          <line x1="${pad.left}" y1="${pad.top + chartH}" x2="${width - pad.right}" y2="${pad.top + chartH}" stroke="${colors.line}"></line>
          <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${pad.top + chartH}" stroke="${colors.line}"></line>
          ${bars}
        </svg>
      `;
    }

    function renderDailyTotalsTable() {
      const data = (dashboardSummary.daily || []).slice().sort((a, b) => String(b.name).localeCompare(String(a.name)));
      const body = document.getElementById("dailyTotalsBody");
      if (!data.length) {
        body.innerHTML = '<tr><td colspan="3">No daily token usage found.</td></tr>';
        return;
      }
      body.innerHTML = data.map(day => `
        <tr>
          <td>${escapeHtml(day.name)}</td>
          <td class="num">${number(day.total_tokens)}</td>
          <td class="num">${number(sessionsForDate(day.name))}</td>
        </tr>
      `).join("");
    }

    function stackedBar(x, y, width, height, input, output, total) {
      const inputWidth = total ? width * input / total : 0;
      const outputWidth = total ? width * output / total : 0;
      return `
        <rect x="${x}" y="${y}" width="${inputWidth}" height="${height}" fill="${colors.input}" rx="3"></rect>
        <rect x="${x + inputWidth}" y="${y}" width="${outputWidth}" height="${height}" fill="${colors.output}" rx="3"></rect>
      `;
    }

    function renderDailyChart() {
      const data = dashboardSummary.daily || [];
      const target = document.getElementById("dailyChart");
      if (!data.length) {
        target.innerHTML = '<div class="empty-state">No token usage records found.</div>';
        return;
      }
      const width = Math.max(720, data.length * 54);
      const height = 280;
      const pad = { top: 18, right: 18, bottom: 58, left: 70 };
      const chartW = width - pad.left - pad.right;
      const chartH = height - pad.top - pad.bottom;
      const maxTotal = Math.max(...data.map(d => Number(d.total_tokens || 0)), 1);
      const barW = Math.max(14, Math.min(34, chartW / data.length * 0.62));
      const gap = chartW / data.length;

      const bars = data.map((d, i) => {
        const total = Number(d.total_tokens || 0);
        const h = chartH * total / maxTotal;
        const x = pad.left + i * gap + (gap - barW) / 2;
        const y = pad.top + chartH - h;
        const input = Number(d.input_tokens || 0);
        const output = Number(d.output_tokens || 0);
        const reasoning = Number(d.reasoning_output_tokens || 0);
        const reasoningH = output ? h * reasoning / Math.max(input + output, 1) : 0;
        return `
          <g>
            <title>${escapeHtml(d.name)}: ${number(total)} tokens</title>
            ${stackedVerticalBar(x, y, barW, h, input, output)}
            <rect x="${x}" y="${Math.max(y, y + h - reasoningH)}" width="${barW}" height="${Math.max(0, reasoningH)}" fill="${colors.reasoning}" opacity="0.8"></rect>
            <text x="${x + barW / 2}" y="${height - 30}" text-anchor="end" transform="rotate(-45 ${x + barW / 2} ${height - 30})" font-size="11" fill="${colors.muted}">${escapeHtml(d.name.slice(5))}</text>
          </g>
        `;
      }).join("");

      target.innerHTML = `
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily token usage chart">
          <line x1="${pad.left}" y1="${pad.top + chartH}" x2="${width - pad.right}" y2="${pad.top + chartH}" stroke="${colors.line}"></line>
          <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${pad.top + chartH}" stroke="${colors.line}"></line>
          <text x="12" y="${pad.top + 8}" font-size="12" fill="${colors.muted}">${number(maxTotal)}</text>
          <text x="12" y="${pad.top + chartH}" font-size="12" fill="${colors.muted}">0</text>
          ${bars}
        </svg>
      `;
    }

    function stackedVerticalBar(x, y, width, height, input, output) {
      const total = Math.max(input + output, 1);
      const outputH = height * output / total;
      const inputH = height - outputH;
      return `
        <rect x="${x}" y="${y}" width="${width}" height="${inputH}" fill="${colors.input}" rx="3"></rect>
        <rect x="${x}" y="${y + inputH}" width="${width}" height="${outputH}" fill="${colors.output}" rx="3"></rect>
      `;
    }

    function renderTopChart() {
      const data = (dashboardSummary.top_sessions || []).slice(0, 12);
      const target = document.getElementById("topChart");
      if (!data.length) {
        target.innerHTML = '<div class="empty-state">No tracked sessions yet.</div>';
        return;
      }
      const width = 620;
      const rowH = 34;
      const height = data.length * rowH + 28;
      const labelW = 154;
      const barW = width - labelW - 80;
      const maxTotal = Math.max(...data.map(d => Number(d.total_tokens || 0)), 1);
      const rows = data.map((d, i) => {
        const y = 18 + i * rowH;
        const w = barW * Number(d.total_tokens || 0) / maxTotal;
        const label = (d.started_local || d.session_id || "").slice(0, 19);
        return `
          <g>
            <title>${escapeHtml(d.session_id)}: ${number(d.total_tokens)} tokens</title>
            <text x="0" y="${y + 15}" font-size="12" fill="${colors.muted}">${escapeHtml(label)}</text>
            <rect x="${labelW}" y="${y}" width="${barW}" height="18" fill="#eef2f7" rx="4"></rect>
            ${stackedBar(labelW, y, w, 18, Number(d.input_tokens || 0), Number(d.output_tokens || 0), Math.max(Number(d.input_tokens || 0) + Number(d.output_tokens || 0), 1))}
            <text x="${labelW + barW + 8}" y="${y + 14}" font-size="12" fill="${colors.muted}">${number(d.total_tokens)}</text>
          </g>
        `;
      }).join("");
      target.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Largest Codex sessions chart">${rows}</svg>`;
    }

    function filteredRows() {
      const q = document.getElementById("search").value.trim().toLowerCase();
      let rows = dashboardRows.slice();
      if (q) {
        rows = rows.filter(row => [
          row.session_id,
          row.machine_name,
          row.machine_id,
          row.model,
          row.cwd,
          row.first_user_message,
          row.status,
          row.relative_file
        ].join(" ").toLowerCase().includes(q));
      }
      rows.sort((a, b) => {
        const av = a[sortKey] ?? "";
        const bv = b[sortKey] ?? "";
        if (typeof av === "number" || typeof bv === "number") {
          return (Number(av || 0) - Number(bv || 0)) * sortDir;
        }
        return String(av).localeCompare(String(bv)) * sortDir;
      });
      return rows;
    }

    function renderTable() {
      const rows = filteredRows();
      const body = document.getElementById("tableBody");
      body.innerHTML = rows.map(row => `
        <tr>
          <td>${escapeHtml(row.started_local || "")}</td>
          <td class="num">${number(row.total_tokens)}</td>
          <td class="num">${number(row.input_tokens)}</td>
          <td class="num">${number(row.cached_input_tokens)}</td>
          <td class="num">${number(row.output_tokens)}</td>
          <td class="num">${number(row.reasoning_output_tokens)}</td>
          <td class="num">${number(row.turns_with_usage)}</td>
          <td>${escapeHtml(row.machine_name || row.machine_id || "unknown")}</td>
          <td>${escapeHtml(row.model || "unknown")}</td>
          <td class="path">${escapeHtml(row.cwd || "unknown")}</td>
          <td class="prompt">${escapeHtml(row.first_user_message || "")}</td>
          <td><span class="pill ${row.has_usage ? "" : "empty"}">${escapeHtml(row.status)}</span></td>
        </tr>
      `).join("");
    }

    function wireTableSort() {
      document.querySelectorAll("th[data-key]").forEach(th => {
        th.addEventListener("click", () => {
          const key = th.dataset.key;
          if (sortKey === key) {
            sortDir *= -1;
          } else {
            sortKey = key;
            sortDir = ["total_tokens", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "turns_with_usage"].includes(key) ? -1 : 1;
          }
          renderTable();
        });
      });
      document.getElementById("search").addEventListener("input", renderTable);
    }

    function renderDashboard() {
      dashboardRows = explorerRows();
      dashboardSummary = aggregateRows(dashboardRows);
      renderFilterSummary(dashboardRows, dashboardSummary);
      renderMetrics();
      renderMachineChart();
      renderMachineTable();
      renderProjectChart();
      renderProjectTable();
      renderDailyTotalChart();
      renderDailyTotalsTable();
      renderDailyChart();
      renderTopChart();
      renderTable();
    }

    renderMeta();
    wireRefreshButton();
    populateFilters();
    wireFilters();
    wireTableSort();
    renderDashboard();
  </script>
</body>
</html>
""".replace("__REPORT_JSON__", report_json)


def write_html(path: Path, report: dict[str, Any]) -> None:
    path.write_text(html_report(report), encoding="utf-8")


def build_report(codex_home: Path, machine_id: str, machine_name: str) -> dict[str, Any]:
    files = iter_session_files(codex_home)
    records = [parse_session_file(path, codex_home) for path in files]
    for record in records:
        record["machine_id"] = machine_id
        record["machine_name"] = machine_name
    records.sort(key=lambda record: record.get("started_at") or "", reverse=True)
    generated_at = datetime.now(timezone.utc)

    return {
        "metadata": {
            "generated_at": generated_at.isoformat(),
            "generated_local": local_display(generated_at),
            "codex_home": str(codex_home),
            "codex_sessions_dir": str(codex_home / "sessions"),
            "machine_id": machine_id,
            "machine_name": machine_name,
            "report_scope": "machine",
            "script_version": "2026-06-03",
        },
        "summary": aggregate(records),
        "records": records,
    }


def machine_snapshot_dir(output_dir: Path) -> Path:
    return output_dir / "machines"


def write_machine_snapshot(report: dict[str, Any], output_dir: Path) -> Path:
    metadata = report.get("metadata", {})
    machine_id = slugify(str(metadata.get("machine_id") or metadata.get("machine_name") or "machine"))
    snapshots_dir = machine_snapshot_dir(output_dir)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshots_dir / f"{machine_id}.json"
    snapshot_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return snapshot_path


def load_machine_reports(output_dir: Path) -> list[dict[str, Any]]:
    snapshots_dir = machine_snapshot_dir(output_dir)
    reports: list[dict[str, Any]] = []
    if not snapshots_dir.exists():
        return reports

    for snapshot_path in sorted(snapshots_dir.glob("*.json")):
        try:
            data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        metadata = data.get("metadata")
        records = data.get("records")
        if not isinstance(metadata, dict) or not isinstance(records, list):
            continue
        machine_id = slugify(str(metadata.get("machine_id") or snapshot_path.stem))
        machine_name = str(metadata.get("machine_name") or machine_id)
        normalized_records: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            row = dict(record)
            row["machine_id"] = str(row.get("machine_id") or machine_id)
            row["machine_name"] = str(row.get("machine_name") or machine_name)
            normalized_records.append(row)
        data["records"] = normalized_records
        reports.append(data)
    return reports


def combine_machine_reports(reports: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc)
    records: list[dict[str, Any]] = []
    machines: list[dict[str, Any]] = []

    for report in reports:
        metadata = report.get("metadata", {})
        machine_id = str(metadata.get("machine_id") or "unknown")
        machine_name = str(metadata.get("machine_name") or machine_id)
        machines.append(
            {
                "machine_id": machine_id,
                "machine_name": machine_name,
                "generated_at": metadata.get("generated_at", ""),
                "generated_local": metadata.get("generated_local", ""),
                "codex_sessions_dir": metadata.get("codex_sessions_dir", ""),
            }
        )
        records.extend(report.get("records", []))

    records.sort(
        key=lambda record: (record.get("started_at") or "", record.get("machine_name") or ""),
        reverse=True,
    )

    return {
        "metadata": {
            "generated_at": generated_at.isoformat(),
            "generated_local": local_display(generated_at),
            "snapshot_dir": str(machine_snapshot_dir(output_dir)),
            "report_scope": "combined",
            "machine_reports": machines,
            "script_version": "2026-06-03",
        },
        "summary": aggregate(records),
        "records": records,
    }


def write_report(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "index.html"
    csv_path = output_dir / "codex-token-usage.csv"
    json_path = output_dir / "codex-token-usage.json"

    write_html(html_path, report)
    write_csv(csv_path, report["records"])
    json_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return {"html": html_path, "csv": csv_path, "json": json_path}


def default_output_dir() -> Path:
    configured = os.environ.get("CODEX_TOKEN_USAGE_OUTPUT_DIR")
    if configured:
        return Path(configured)
    return Path.home() / "Downloads" / "codex-token-usage"


def parse_args(argv: list[str]) -> argparse.Namespace:
    default_codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    machine_name = default_machine_name()
    machine_id = os.environ.get("CODEX_TOKEN_USAGE_MACHINE_ID", "")

    parser = argparse.ArgumentParser(description="Generate a local Codex token usage HTML report.")
    parser.add_argument(
        "--codex-home",
        default=str(default_codex_home),
        help="Codex home directory. Default: ~/.codex or CODEX_HOME.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(default_output_dir()),
        help="Directory for index.html, CSV, and JSON. Default: ~/Downloads/codex-token-usage or CODEX_TOKEN_USAGE_OUTPUT_DIR.",
    )
    parser.add_argument(
        "--machine-name",
        default=machine_name,
        help="Label for this computer in shared reports. Default: hostname or CODEX_TOKEN_USAGE_MACHINE_NAME.",
    )
    parser.add_argument(
        "--machine-id",
        default=machine_id,
        help="Stable ID for this computer's snapshot file. Default: CODEX_TOKEN_USAGE_MACHINE_ID or slug of --machine-name.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    codex_home = Path(args.codex_home).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    machine_name = str(args.machine_name or default_machine_name())
    machine_id = slugify(str(args.machine_id or machine_name))

    local_report = build_report(codex_home, machine_id, machine_name)
    snapshot_path = write_machine_snapshot(local_report, output_dir)
    report = combine_machine_reports(load_machine_reports(output_dir), output_dir)
    paths = write_report(report, output_dir)
    totals = report["summary"]["totals"]

    print(f"Wrote {snapshot_path}")
    print(f"Wrote {paths['html']}")
    print(f"Wrote {paths['csv']}")
    print(f"Wrote {paths['json']}")
    print(
        "Tracked {tracked}/{all_sessions} sessions across {machines} computers, total tokens: {tokens}".format(
            tracked=report["summary"]["tracked_session_count"],
            all_sessions=report["summary"]["session_count"],
            machines=report["summary"].get("machine_count", 0),
            tokens=f"{totals['total_tokens']:,}",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
