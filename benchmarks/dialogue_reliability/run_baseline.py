#!/usr/bin/env python3
"""Record pre-change inference/app metrics. Does not retune MLX server flags."""
from __future__ import annotations

import argparse
import codecs
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = Path(__file__).resolve().parent / "runs"
CODE_DEFAULTS = {
    "model": "qwen3.5-9b-hauhau-aggressive-mxfp4",
    "enable_thinking": True,
    "reasoning_effort": "medium",
    "thinking_budget_medium": 1024,
    "default_max_tokens": 8192,
    "temperature_thinking": 0.6,
    "top_p_thinking": 0.95,
    "top_k": 20,
    "temperature_non_thinking": 0.7,
    "top_p_non_thinking": 0.8,
    "practical_prompt_budget": 32768,
    "recent_keep_messages": 8,
    "mlx_prefill_step_size": 1024,
    "mlx_prompt_cache_size": 4,
    "mlx_prompt_cache_bytes": "4G",
    "note": "Frontend tok/s currently uses output_tokens / total_elapsed (includes TTFT).",
}


def _sse_events(raw: str) -> list[tuple[str, object]]:
    events: list[tuple[str, object]] = []
    for block in raw.replace("\r\n", "\n").split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        data = "\n".join(data_lines)
        if data == "[DONE]":
            events.append(("done_wire", "[DONE]"))
            continue
        if not data:
            continue
        try:
            events.append((event, json.loads(data)))
        except json.JSONDecodeError:
            events.append((event, data))
    return events


def _post_chat(api: str, body: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        api.rstrip("/") + "/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    t0 = time.perf_counter()
    headers_s = None
    first_visible_s = None
    first_any_s = None
    raw = ""
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        headers_s = time.perf_counter() - t0
        while True:
            chunk = resp.read(128)
            if not chunk:
                raw += decoder.decode(b"", final=True)
                break
            raw += decoder.decode(chunk)
            now = time.perf_counter() - t0
            for event, data in _sse_events(raw):
                if event != "delta" or not isinstance(data, dict):
                    continue
                if first_any_s is None and (data.get("content") or data.get("reasoning")):
                    first_any_s = now
                if first_visible_s is None and data.get("content"):
                    first_visible_s = now
                    break
    elapsed = time.perf_counter() - t0
    events = _sse_events(raw)
    content = ""
    reasoning = ""
    usage = {}
    finish = None
    conversation_id = None
    malformed = 0
    saw_done = False
    saw_app_done = False
    for event, data in events:
        if event == "done_wire":
            saw_done = True
        elif event == "meta" and isinstance(data, dict):
            conversation_id = data.get("conversation_id")
        elif event == "delta" and isinstance(data, dict):
            content += data.get("content") or ""
            reasoning += data.get("reasoning") or ""
        elif event == "usage" and isinstance(data, dict):
            usage = data
        elif event == "done" and isinstance(data, dict):
            saw_app_done = True
            finish = data.get("finish_reason")
            usage = data.get("usage") or usage
            msg = data.get("message") or {}
            content = msg.get("content") or content
            reasoning = msg.get("reasoning_content") or reasoning
        elif isinstance(data, str):
            malformed += 1
    output = int((usage or {}).get("completion_tokens") or (usage or {}).get("output") or 0)
    prompt = int((usage or {}).get("prompt_tokens") or (usage or {}).get("input") or 0)
    cached = int((usage or {}).get("cached") or (usage or {}).get("cached_tokens") or 0)
    server_ttft = None
    server_decode = None
    for event, data in events:
        if event in {"usage", "done"} and isinstance(data, dict):
            metrics = data.get("metrics") or data
            if metrics.get("ttft_ms") is not None:
                server_ttft = float(metrics["ttft_ms"]) / 1000
            if metrics.get("decode_tokens_per_sec") is not None:
                server_decode = metrics.get("decode_tokens_per_sec")
    ttft = server_ttft if server_ttft is not None else (first_visible_s or first_any_s)
    decode_s = None
    if first_any_s is not None and elapsed > first_any_s:
        decode_s = elapsed - first_any_s
    return {
        "conversation_id": conversation_id,
        "headers_s": headers_s,
        "ttft_s": ttft,
        "total_latency_s": elapsed,
        "prompt_tokens": prompt,
        "completion_tokens": output,
        "cached_tokens": cached,
        "cache_hit_ratio": (cached / prompt) if prompt else None,
        "effective_output_tok_s": (output / elapsed) if elapsed and output else None,
        "decode_tok_s": server_decode
        if server_decode is not None
        else ((output / decode_s) if decode_s and output else None),
        "probe_first_delta_s": first_any_s,
        "probe_first_visible_s": first_visible_s,
        "finish_reason": finish,
        "saw_app_done": saw_app_done,
        "saw_done_wire": saw_done,
        "malformed_sse_frames": malformed,
        "thinking_chars": len(reasoning),
        "visible_chars": len(content),
        "content": content,
        "content_preview": content[:240],
    }


def _delete(api: str, conversation_id: str) -> None:
    req = urllib.request.Request(
        api.rstrip("/") + f"/conversation/{conversation_id}",
        method="DELETE",
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except urllib.error.HTTPError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    cases = [
        {
            "name": "current_default_thinking_short",
            "body": {
                "message": "[kiln-bench] 用一两句中文继续：雨停了，门口还亮着一盏灯。",
                "stream": True,
                "enable_thinking": True,
                "reasoning_effort": "medium",
                "max_tokens": 64,
            },
        },
        {
            "name": "thinking_off_short",
            "body": {
                "message": "[kiln-bench] 用一两句中文继续：雨停了，门口还亮着一盏灯。",
                "stream": True,
                "enable_thinking": False,
                "max_tokens": 64,
            },
        },
        {
            "name": "thinking_off_dialogue_256",
            "body": {
                "message": "[kiln-bench] 角色在深夜书房。用户说：钥匙还在你那儿吗？请用自然中文推进互动，不要重复上一句。",
                "stream": True,
                "enable_thinking": False,
                "max_tokens": 256,
            },
        },
    ]
    results = []
    for case in cases:
        row = {"name": case["name"]}
        try:
            measured = _post_chat(args.api, case["body"], args.timeout)
            row.update(measured)
            if measured.get("conversation_id") and not args.keep:
                _delete(args.api, measured["conversation_id"])
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc)
        results.append(row)
        print(json.dumps(row, ensure_ascii=False))
    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "code_defaults": CODE_DEFAULTS,
        "api": args.api,
        "results": results,
    }
    out = RUNS / "baseline-prechange.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
