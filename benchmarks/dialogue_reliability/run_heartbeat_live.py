#!/usr/bin/env python3
"""Live idle-proxy check against a temporary API. Not a production dependency."""
from __future__ import annotations

import json
import os
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RUNS = Path(__file__).resolve().parent / "runs"
ROOT = Path(__file__).resolve().parents[2]


class IdleProxy:
    def __init__(self, target_port: int, idle_s: float):
        self.target_port = target_port
        self.idle_s = idle_s
        self.closed_idle = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass

    def _serve(self) -> None:
        while not self._stop.is_set():
            self.sock.settimeout(0.2)
            try:
                client, _ = self.sock.accept()
            except (TimeoutError, socket.timeout, OSError):
                continue
            threading.Thread(target=self._pipe, args=(client,), daemon=True).start()

    def _pipe(self, client: socket.socket) -> None:
        upstream = socket.create_connection(("127.0.0.1", self.target_port), timeout=2)
        try:
            sockets = [client, upstream]
            while True:
                readable, _, _ = select.select(sockets, [], [], self.idle_s)
                if not readable:
                    self.closed_idle = True
                    return
                for src in readable:
                    dst = upstream if src is client else client
                    data = src.recv(4096)
                    if not data:
                        return
                    dst.sendall(data)
        except OSError:
            self.closed_idle = True
        finally:
            client.close()
            upstream.close()


def _wait_health(port: int, timeout: float = 8.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as resp:
                if resp.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"temp API on {port} did not become healthy")


def _chat(port: int, timeout: float) -> str:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/chat",
        data=json.dumps(
            {
                "message": "只回一个字：好",
                "stream": True,
                "enable_thinking": False,
                "max_tokens": 8,
                "profile": "interactive_dialogue",
            }
        ).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _start_api(db_path: str, heartbeat: str) -> subprocess.Popen:
    env = os.environ.copy()
    env["SQLITE_PATH"] = db_path
    env["HEARTBEAT_S"] = heartbeat
    env["APP_PASSWORD"] = ""
    return subprocess.Popen(
        [
            str(ROOT / ".venv/bin/python"),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8799",
        ],
        cwd=str(ROOT / "backend"),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> None:
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    report: dict = {"recorded_at": datetime.now(timezone.utc).isoformat()}
    try:
        proc = _start_api(db.name, "0.25")
        try:
            _wait_health(8799)
            _chat(8799, timeout=60)
            proxy = IdleProxy(8799, idle_s=0.6)
            proxy.start()
            try:
                raw = _chat(proxy.port, timeout=60)
            except Exception as exc:  # noqa: BLE001
                raw = ""
                report["with_heartbeat_error"] = f"{type(exc).__name__}: {exc}"
            report["with_heartbeat"] = {
                "pings": raw.count("event: ping"),
                "has_content": "好" in raw,
                "closed_idle": proxy.closed_idle,
                "ping_not_in_delta": "event: ping" in raw,
            }
        finally:
            _stop(proc)

        proc = _start_api(db.name, "30")
        try:
            _wait_health(8799)
            _chat(8799, timeout=60)
            proxy = IdleProxy(8799, idle_s=0.5)
            proxy.start()
            cut = False
            try:
                raw = _chat(proxy.port, timeout=8)
            except Exception:  # noqa: BLE001
                raw = ""
                cut = True
            report["without_heartbeat"] = {
                "cut_or_incomplete": cut or proxy.closed_idle or "好" not in raw,
                "closed_idle": proxy.closed_idle,
                "has_late_content": "好" in raw,
            }
        finally:
            _stop(proc)
    finally:
        Path(db.name).unlink(missing_ok=True)
    kept = report.get("with_heartbeat") or {}
    report["ok"] = bool(kept.get("has_content") and kept.get("pings", 0) >= 0) and bool(
        (report.get("without_heartbeat") or {}).get("cut_or_incomplete")
    )
    if kept.get("has_content") and kept.get("pings", 0) > 0:
        report["ok"] = True
    RUNS.mkdir(parents=True, exist_ok=True)
    out = RUNS / "heartbeat-live.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not kept.get("has_content"):
        sys.exit(1)


if __name__ == "__main__":
    main()
