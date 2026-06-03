#!/usr/bin/env python3
"""
Serve the Codex token usage report locally and expose a refresh endpoint.

Bind address is 127.0.0.1 only. POST /refresh reruns the configured
codex_token_usage_report.py generator, then the browser reloads index.html.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class TokenUsageHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args: Any,
        directory: str | None = None,
        generator: str | None = None,
        generator_args: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        self.generator = generator
        self.generator_args = generator_args or []
        super().__init__(*args, directory=directory, **kwargs)

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/refresh":
            self.send_json(404, {"ok": False, "error": "Not found"})
            return

        report_dir = Path(self.directory).resolve()
        script = Path(self.generator or "").expanduser().resolve()
        if not script.exists():
            self.send_json(500, {"ok": False, "error": f"Missing generator: {script}"})
            return

        try:
            result = subprocess.run(
                [sys.executable, "-B", str(script), "--output-dir", str(report_dir), *self.generator_args],
                cwd=str(report_dir),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError as exc:
            self.send_json(500, {"ok": False, "error": str(exc)})
            return

        if result.returncode != 0:
            self.send_json(
                500,
                {
                    "ok": False,
                    "error": (result.stderr or result.stdout or f"exit {result.returncode}").strip(),
                },
            )
            return

        self.send_json(200, {"ok": True, "stdout": result.stdout.strip()})

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the Codex token usage report with a refresh endpoint.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("CODEX_TOKEN_USAGE_PORT", "8765")))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--directory", default=os.environ.get("CODEX_TOKEN_USAGE_OUTPUT_DIR", str(Path.home() / "Downloads" / "codex-token-usage")))
    parser.add_argument("--generator", default=str(Path(__file__).resolve().parent / "codex_token_usage_report.py"))
    parser.add_argument("--machine-name", default=None)
    parser.add_argument("--machine-id", default=None)
    parser.add_argument("--daemonize", action="store_true", help="Detach into the background before serving.")
    parser.add_argument("--log-file", default=None, help="Log file to use with --daemonize.")
    parser.add_argument("--pid-file", default=None, help="Write the background server PID to this file.")
    return parser.parse_args(argv)


def daemonize(log_file: str | None) -> int | None:
    if not hasattr(os, "fork"):
        raise RuntimeError("--daemonize requires a POSIX-like system")

    pid = os.fork()
    if pid > 0:
        return pid

    os.setsid()
    os.chdir("/")

    stdin_fd = os.open(os.devnull, os.O_RDONLY)
    os.dup2(stdin_fd, sys.stdin.fileno())
    os.close(stdin_fd)

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        output_fd = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    else:
        output_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(output_fd, sys.stdout.fileno())
    os.dup2(output_fd, sys.stderr.fileno())
    os.close(output_fd)
    return None


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    directory = str(Path(args.directory).expanduser().resolve())
    generator = str(Path(args.generator).expanduser().resolve())
    generator_args: list[str] = []
    if args.machine_name:
        generator_args.extend(["--machine-name", args.machine_name])
    if args.machine_id:
        generator_args.extend(["--machine-id", args.machine_id])

    if args.daemonize:
        child_pid = daemonize(args.log_file)
        if child_pid is not None:
            if args.pid_file:
                pid_path = Path(args.pid_file).expanduser().resolve()
                pid_path.parent.mkdir(parents=True, exist_ok=True)
                pid_path.write_text(f"{child_pid}\n", encoding="utf-8")
            return 0

    def handler(*handler_args: Any, **handler_kwargs: Any) -> TokenUsageHandler:
        return TokenUsageHandler(
            *handler_args,
            directory=directory,
            generator=generator,
            generator_args=generator_args,
            **handler_kwargs,
        )

    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/index.html"
    print(f"Serving {directory}", flush=True)
    print(f"Open {url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
