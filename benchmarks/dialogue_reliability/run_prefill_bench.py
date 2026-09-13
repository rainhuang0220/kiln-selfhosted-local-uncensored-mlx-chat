#!/usr/bin/env python3
"""Measure mlx-lm --prefill-step-size only. Does not change production flags."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from run_baseline import RUNS, _post_chat

STEPS = (512, 1024, 2048)
MODEL = "/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4"
PYTHON = Path(__file__).resolve().parents[2] / ".venv/bin/python"


def _wait_mlx(timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen("http://127.0.0.1:8081/health", timeout=1).read()
            return True
        except OSError:
            time.sleep(0.5)
    return False


def _start_mlx(step: int) -> subprocess.Popen:
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
            "4",
            "--prompt-cache-bytes",
            "4G",
            "--chat-template-args",
            '{"enable_thinking":false,"reasoning_effort":"medium"}',
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8787")
    parser.add_argument("--apply", action="store_true", help="stop LaunchAgent mlx and swap prefill sizes")
    args = parser.parse_args()
    if not args.apply:
        print("refusing to mutate the production mlx server; pass --apply after eval")
        return
    subprocess.run(["launchctl", "stop", f"gui/{os.getuid()}/com.kiln.mlx"], check=False)
    time.sleep(1)
    report = {"recorded_at": datetime.now(timezone.utc).isoformat(), "steps": []}
    try:
        for step in STEPS:
            proc = _start_mlx(step)
            try:
                if not _wait_mlx():
                    report["steps"].append({"prefill_step_size": step, "error": "mlx start timeout"})
                    continue
                row = _post_chat(
                    args.api,
                    {
                        "message": "用八十个汉字描写雨停后的书店，不要停。",
                        "stream": True,
                        "enable_thinking": False,
                        "max_tokens": 64,
                        "profile": "interactive_dialogue",
                    },
                    120,
                )
                report["steps"].append({"prefill_step_size": step, **row})
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                time.sleep(1)
    finally:
        subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.kiln.mlx"], check=False)
    RUNS.mkdir(parents=True, exist_ok=True)
    out = RUNS / "prefill-step.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
