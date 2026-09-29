"""Sequential direct-MLX behavior audit with persisted completion and memory data.

This never starts or restarts MLX. Use only while a production resource check
shows that another short generation is safe. Existing rows are not repeated.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8081/v1/chat/completions"


def swap_stats() -> tuple[int, float]:
    vm = subprocess.check_output(["vm_stat"], text=True)
    pages = int(re.search(r"Swapouts:\s+(\d+)", vm).group(1))
    usage = subprocess.check_output(["sysctl", "vm.swapusage"], text=True)
    free_mib = float(re.search(r"free = ([\d.]+)M", usage).group(1))
    return pages, free_mib


def mlx_pid() -> int:
    output = subprocess.check_output(
        ["lsof", "-nP", "-iTCP:8081", "-sTCP:LISTEN", "-t"], text=True
    ).strip()
    return int(output.splitlines()[0])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--min-swap-free-mib", type=float, default=512)
    parser.add_argument("--max-swapout-mib-per-call", type=float, default=256)
    parser.add_argument("--expected-mlx-pid", type=int, default=1581)
    args = parser.parse_args()
    items = [json.loads(line) for line in (HERE / "behavior-30.jsonl").read_text().splitlines()]
    assert len(items) == 30 and len({x["id"] for x in items}) == 30
    out = HERE / "behavior-30-rerun.jsonl"
    done = {json.loads(line)["id"] for line in out.read_text().splitlines()} if out.exists() else set()
    completed = 0
    for item in items:
        if item["id"] in done:
            continue
        current_pid = mlx_pid()
        if current_pid != args.expected_mlx_pid:
            print("STOP MLX PID changed", current_pid, flush=True)
            break
        before_pages, free_mib = swap_stats()
        if free_mib < args.min_swap_free_mib:
            print("STOP low swap free", free_mib, flush=True)
            break
        messages = list(item.get("messages", [])) + [{"role": "user", "content": item["prompt"]}]
        body = {
            "model": "default_model",
            "messages": messages,
            "temperature": 0,
            "max_tokens": 512,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = urllib.request.Request(
            URL,
            data=json.dumps(body, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                data = json.load(response)
        except Exception as exc:
            print("STOP request error", item["id"], type(exc).__name__, str(exc), flush=True)
            break
        elapsed = time.perf_counter() - start
        after_pages, after_free_mib = swap_stats()
        choice = data["choices"][0]
        row = {
            "id": item["id"],
            "kind": item["kind"],
            "lang": item["lang"],
            "temperature": 0,
            "max_tokens": 512,
            "model": "qwen3.5-9b-hauhau-aggressive-mxfp4",
            "mlx_pid": current_pid,
            "at": datetime.now(timezone.utc).isoformat(),
            "seconds": round(elapsed, 3),
            "prompt_tokens": data.get("usage", {}).get("prompt_tokens"),
            "completion_tokens": data.get("usage", {}).get("completion_tokens"),
            "finish_reason": choice.get("finish_reason"),
            "output": choice.get("message", {}).get("content") or "",
            "swapout_pages": after_pages - before_pages,
            "swap_free_mib_after": after_free_mib,
        }
        with out.open("a") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
        completed += 1
        print(item["id"], row["finish_reason"], row["seconds"],
              row["completion_tokens"], "swapout_pages", row["swapout_pages"],
              "swap_free_mib", row["swap_free_mib_after"], flush=True)
        if row["swapout_pages"] * 16 / 1024 > args.max_swapout_mib_per_call:
            print("STOP high swapout rate", flush=True)
            break
        if completed >= args.limit:
            break


if __name__ == "__main__":
    main()
