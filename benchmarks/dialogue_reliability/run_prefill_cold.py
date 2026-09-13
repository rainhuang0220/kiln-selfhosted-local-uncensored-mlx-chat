#!/usr/bin/env python3
"""Cold prefill-step-size comparison. Stops LaunchAgent mlx; restores it after."""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RUNS = Path(__file__).resolve().parent / "runs"
MODEL = "/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4"
PYTHON = Path(__file__).resolve().parents[2] / ".venv/bin/python"
UID = os.getuid()


def _port_free() -> bool:
    try:
        urllib.request.urlopen("http://127.0.0.1:8081/health", timeout=0.4).read()
        return False
    except OSError:
        return True


def _wait(pred, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.4)
    return False


def _start(step: int) -> subprocess.Popen:
    return subprocess.Popen(
        [
            str(PYTHON),
            "-m",
            "mlx_lm.server",
            "--model",
            MODEL,
            "--host",
            "127.0.0.1",
            "--port",
            "8081",
            "--prefill-step-size",
            str(step),
            "--decode-concurrency",
            "1",
            "--prompt-concurrency",
            "1",
            "--prompt-cache-size",
            "2",
            "--chat-template-args",
            '{"enable_thinking":false}',
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _rss(pid: int) -> int | None:
    try:
        out = subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)], text=True)
        return int(out.strip() or 0)
    except Exception:  # noqa: BLE001
        return None


def _cold_ttft(prompt: str) -> dict:
    body = {
        "model": "default_model",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8,
        "stream": True,
        "temperature": 0.7,
        "chat_template_kwargs": {"enable_thinking": False},
        "stream_options": {"include_usage": True},
    }
    req = urllib.request.Request(
        "http://127.0.0.1:8081/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    first = None
    raw = b""
    with urllib.request.urlopen(req, timeout=180) as resp:
        while True:
            chunk = resp.read(256)
            if not chunk:
                break
            raw += chunk
            if first is None and b"content" in chunk:
                first = time.perf_counter() - t0
    text = raw.decode("utf-8", "replace")
    usage = {}
    for block in text.split("\n\n"):
        line = block.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            continue
        try:
            ev = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if ev.get("usage"):
            usage = ev["usage"]
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    return {
        "ttft_s": first,
        "total_s": time.perf_counter() - t0,
        "prompt_tokens": prompt_tokens,
        "cached_tokens": int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
    }


def main() -> None:
    prompt = ("雨停了，旧书店的灯还亮着。钥匙还在原处。" * 220)
    subprocess.run(["launchctl", "stop", f"gui/{UID}/com.kiln.mlx"], check=False)
    if not _wait(_port_free, 20):
        subprocess.run(["launchctl", "kill", "SIGTERM", f"gui/{UID}/com.kiln.mlx"], check=False)
        _wait(_port_free, 15)
    rows = []
    try:
        for step in (512, 1024, 2048):
            proc = _start(step)
            if not _wait(lambda: not _port_free(), 90):
                rows.append({"prefill_step_size": step, "error": "start timeout"})
                proc.kill()
                continue
            time.sleep(1)
            measured = _cold_ttft(prompt)
            measured["prefill_step_size"] = step
            measured["rss_kb"] = _rss(proc.pid)
            rows.append(measured)
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            _wait(_port_free, 20)
    finally:
        subprocess.run(["launchctl", "kickstart", "-k", f"gui/{UID}/com.kiln.mlx"], check=False)
    report = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "note": "Cold mlx-direct prompts. Previous short-prompt kiln run is invalid.",
        "rows": rows,
    }
    RUNS.mkdir(parents=True, exist_ok=True)
    out = RUNS / "prefill-step-cold.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
