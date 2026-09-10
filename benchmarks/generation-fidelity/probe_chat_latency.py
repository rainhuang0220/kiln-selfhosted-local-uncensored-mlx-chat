#!/usr/bin/env python3
"""Measure chat stream stages. Writes gitignored JSON under runs/."""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"


def _stream(url: str, message: str, enable_thinking: bool, timeout: int = 120) -> dict:
    body = json.dumps(
        {
            "message": message,
            "stream": True,
            "enable_thinking": enable_thinking,
            "reasoning_effort": "medium",
            "max_tokens": 128,
        }
    ).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/chat",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    t0 = time.perf_counter()
    marks = {
        "request_start": 0.0,
        "headers": None,
        "meta": None,
        "first_reasoning": None,
        "first_content": None,
        "done": None,
    }
    reasoning_n = 0
    content_n = 0
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        marks["headers"] = time.perf_counter() - t0
        buf = ""
        while True:
            chunk = resp.read(64)
            if not chunk:
                break
            buf += chunk.decode("utf-8", "replace")
            while "\n\n" in buf:
                raw, buf = buf.split("\n\n", 1)
                event = "message"
                data = ""
                for line in raw.split("\n"):
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        data = line[5:].strip()
                if data == "[DONE]":
                    marks["done"] = time.perf_counter() - t0
                    break
                if not data or data[0] != "{":
                    continue
                payload = json.loads(data)
                now = time.perf_counter() - t0
                if event == "meta" and marks["meta"] is None:
                    marks["meta"] = now
                if event == "delta":
                    if payload.get("reasoning") and marks["first_reasoning"] is None:
                        marks["first_reasoning"] = now
                    if payload.get("content") and marks["first_content"] is None:
                        marks["first_content"] = now
                    reasoning_n += len(payload.get("reasoning") or "")
                    content_n += len(payload.get("content") or "")
            if marks["done"] is not None:
                break
    if marks["done"] is None:
        marks["done"] = time.perf_counter() - t0
    visible = marks["first_content"]
    think = None
    if marks["first_reasoning"] is not None and visible is not None:
        think = round(visible - marks["first_reasoning"], 3)
    decode_s = None
    if visible is not None:
        decode_s = max(0.001, marks["done"] - visible)
    return {
        "url": url,
        "enable_thinking": enable_thinking,
        "marks_s": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in marks.items()},
        "reasoning_chars": reasoning_n,
        "content_chars": content_n,
        "ttft_s": marks["first_reasoning"] or marks["first_content"] or marks["headers"],
        "thinking_to_visible_s": think,
        "visible_answer_s": visible,
        "decode_chars_per_s": round(content_n / decode_s, 1) if decode_s and content_n else None,
        "total_s": marks["done"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", default="http://127.0.0.1:8787")
    parser.add_argument("--public", default="")
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    rows = []
    for url in [args.local] + ([args.public] if args.public else []):
        for thinking in (True, False):
            for i in range(args.repeat):
                msg = f"Reply with exactly the word pong and nothing else. n={i}"
                print(f"{url} thinking={thinking} #{i}", flush=True)
                try:
                    row = _stream(url, msg, thinking)
                except Exception as exc:  # noqa: BLE001
                    row = {"url": url, "enable_thinking": thinking, "error": str(exc)[:300]}
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
                time.sleep(0.4)
    dest = RUNS / "chat-latency.json"
    dest.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", dest)


if __name__ == "__main__":
    main()
