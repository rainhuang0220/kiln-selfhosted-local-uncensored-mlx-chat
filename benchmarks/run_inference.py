#!/usr/bin/env python3
"""HTTP inference benchmark against a running mlx_lm.server.

Does not load weights in this process. Records TTFT / decode tok/s / RSS.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = Path(os.environ.get("MODEL_PATH", ROOT.parent / "qwen3.8-27b"))


def pid_on_port(port: int) -> int | None:
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            text=True,
        ).strip()
        return int(out.splitlines()[0]) if out else None
    except (subprocess.CalledProcessError, ValueError):
        return None


def rss_mb(pid: int | None) -> float | None:
    if not pid:
        return None
    try:
        kb = int(
            subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)], text=True).strip()
        )
        return round(kb / 1024, 1)
    except (subprocess.CalledProcessError, ValueError):
        return None


def load_tokenizer():
    from tokenizers import Tokenizer

    path = MODEL / "tokenizer.json"
    if not path.exists():
        raise SystemExit(f"missing tokenizer: {path}")
    return Tokenizer.from_file(str(path))


def make_prompt(tok, n_tokens: int) -> str:
    piece = "The quick brown fox jumps over the lazy dog. "
    text = piece
    while len(tok.encode(text).ids) < n_tokens:
        text += piece
    ids = tok.encode(text).ids[:n_tokens]
    # decode may not be exact length; close enough for labeling
    return tok.decode(ids)


def stream_chat(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    t0 = time.perf_counter()
    ttft = None
    first_keepalive = None
    last_keepalive = None
    content = ""
    reasoning = ""
    usage = {}
    completion_tokens_seen = 0
    try:
        with urllib.request.urlopen(req, timeout=body.get("max_tokens", 200) * 4 + 120) as resp:
            buf = ""
            while True:
                chunk = resp.read(256)
                if not chunk:
                    break
                now = time.perf_counter()
                buf += chunk.decode("utf-8", errors="replace")
                buf = buf.replace("\r\n", "\n")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip("\r")
                    if not line:
                        continue
                    if line.startswith(":"):
                        if first_keepalive is None:
                            first_keepalive = now - t0
                        last_keepalive = now - t0
                        continue
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        total = time.perf_counter() - t0
                        decode_s = None
                        if ttft is not None:
                            decode_s = max(1e-6, total - ttft)
                        out_tok = int(usage.get("completion_tokens") or completion_tokens_seen)
                        return {
                            "ok": True,
                            "ttft_s": ttft,
                            "total_s": total,
                            "prefill_keepalive_first_s": first_keepalive,
                            "prefill_keepalive_last_s": last_keepalive,
                            "decode_s": decode_s,
                            "decode_tok_s": (out_tok / decode_s) if decode_s and out_tok else None,
                            "prompt_tokens": usage.get("prompt_tokens"),
                            "completion_tokens": usage.get("completion_tokens") or out_tok,
                            "cached_tokens": (usage.get("prompt_tokens_details") or {}).get(
                                "cached_tokens"
                            ),
                            "content_chars": len(content),
                            "reasoning_chars": len(reasoning),
                            "finish": True,
                        }
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("usage"):
                        usage = obj["usage"]
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content") or delta.get("reasoning") or ""
                    if delta.get("content"):
                        content += delta["content"]
                        completion_tokens_seen += 1
                    if delta.get("reasoning"):
                        reasoning += delta["reasoning"]
                        completion_tokens_seen += 1
                    if piece and ttft is None:
                        ttft = time.perf_counter() - t0
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code}: {exc.read()[:300].decode()}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "stream ended without [DONE]"}


def run_case(name: str, prompt_tokens: int, max_tokens: int, args, tok) -> dict:
    prompt = make_prompt(tok, prompt_tokens)
    pid = pid_on_port(args.port)
    rss_before = rss_mb(pid)
    url = f"http://{args.host}:{args.port}/v1/chat/completions"
    body = {
        "model": "default_model",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {
            "enable_thinking": args.thinking,
            "reasoning_effort": "low",
            "preserve_thinking": False,
        },
    }
    result = stream_chat(url, body)
    rss_after = rss_mb(pid)
    result.update(
        {
            "name": name,
            "requested_prompt_tokens": prompt_tokens,
            "requested_max_tokens": max_tokens,
            "enable_thinking": args.thinking,
            "rss_before_mb": rss_before,
            "rss_after_mb": rss_after,
            "pid": pid,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8081)
    p.add_argument("--out", default=str(ROOT / "benchmarks" / "baseline" / "baseline.json"))
    p.add_argument("--thinking", action="store_true")
    p.add_argument(
        "--cases",
        default="A,B",
        help="Comma subset of A,B,C,D (D=8k can OOM on 24GB)",
    )
    args = p.parse_args()
    tok = load_tokenizer()
    catalog = {
        "A": (100, 100),
        "B": (1000, 200),
        "C": (4000, 200),
        "D": (8000, 200),
    }
    wanted = [c.strip().upper() for c in args.cases.split(",") if c.strip()]
    results = []
    for name in wanted:
        if name not in catalog:
            print(f"unknown case {name}", file=sys.stderr)
            continue
        n_in, n_out = catalog[name]
        print(f"== {name} prompt≈{n_in} max_tokens={n_out} thinking={args.thinking}", flush=True)
        row = run_case(name, n_in, n_out, args, tok)
        print(json.dumps({k: row.get(k) for k in ("ok", "ttft_s", "decode_tok_s", "total_s", "prompt_tokens", "completion_tokens", "cached_tokens", "rss_after_mb", "error")}), flush=True)
        results.append(row)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "hardware": "Apple M4 24GB",
        "model": str(MODEL),
        "server": f"{args.host}:{args.port}",
        "thinking": args.thinking,
        "results": results,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if all(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
