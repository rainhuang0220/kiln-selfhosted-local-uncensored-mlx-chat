#!/usr/bin/env python3
"""Client-side MLX bench. Refuses to run unless KILN_ALLOW_BENCH=1.

Records client TTFT, decode, and the server's prompt-progress lines.
Stops the sweep if the MLX footprint or jetsam level crosses a guard.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from tokenizers import Tokenizer

ROOT = Path("/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4")
ERR = Path("/tmp/kiln-mlx.err")
OUT = Path("/Users/rainhuang/Desktop/models/kiln/engineering/2026-09-24/benchmark-results")
MODEL = str(ROOT)
URL = os.environ.get("KILN_MLX_URL", "http://127.0.0.1:8081/v1/chat/completions")
PID = int(os.environ.get("KILN_MLX_PID", "1581"))


def die_if_locked() -> None:
    if os.environ.get("KILN_ALLOW_BENCH") != "1":
        raise SystemExit("refusing: set KILN_ALLOW_BENCH=1")


def footprint_mb() -> int | None:
    try:
        text = subprocess.check_output(["footprint", "-p", str(PID)], text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for line in text.splitlines():
        if "phys_footprint:" in line and "peak" not in line:
            parts = line.split()
            for p in parts:
                if p.isdigit():
                    return int(p) // (1024 * 1024) if int(p) > 10_000 else int(p)
            # "phys_footprint: 5086 MB"
            if "MB" in line:
                num = line.split("phys_footprint:")[1].strip().split()[0]
                return int(float(num))
    return None


def jetsam_level() -> int | None:
    try:
        text = subprocess.check_output(["sysctl", "-n", "kern.memorystatus_level"], text=True)
        return int(text.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None


def build_cjk(n_chars: int) -> str:
    parts: list[str] = []
    n = 0
    i = 0
    while n < n_chars:
        s = (
            f"第{i}条记录：地点编号{i * 7 + 3}，日期2024年{(i % 12) + 1}月{(i % 27) + 1}日，"
            f"金额{(i * 13) % 10000}元。当事人甲{i}与乙{i}签署条款，不是豁免，不得转让。"
            f"函数名 handle_case_{i} 返回 False。\n"
        )
        parts.append(s)
        n += len(s)
        i += 1
    return "".join(parts)[:n_chars]


def build_tokens(tok: Tokenizer, n_tokens: int) -> str:
    # Grow English-like unique text until the tokenizer reports >= n_tokens, then trim ids.
    lo, hi = n_tokens // 2, n_tokens * 4
    text = ""
    ids: list[int] = []
    for _ in range(18):
        mid = (lo + hi) // 2
        text = " ".join(f"item{i} value{(i * 17) % 997} section{i % 50}" for i in range(max(1, mid)))
        ids = tok.encode(text).ids
        if len(ids) < n_tokens:
            lo = mid + 1
        else:
            hi = mid
        if lo >= hi:
            break
    ids = tok.encode(text).ids
    if len(ids) < n_tokens:
        raise RuntimeError(f"could not build {n_tokens} tokens, got {len(ids)}")
    return tok.decode(ids[:n_tokens])


def err_len() -> int:
    try:
        return ERR.stat().st_size
    except OSError:
        return 0


def stream(content: str, max_tokens: int) -> dict:
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
    }
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    ttft = None
    pieces: list[str] = []
    finish = None
    n_data = 0
    with urllib.request.urlopen(req, timeout=600) as resp:
        status = resp.status
        buf = b""
        while True:
            b = resp.read(1)
            if not b:
                break
            buf += b
            if b != b"\n":
                continue
            line = buf.decode("utf-8", "replace").strip()
            buf = b""
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            n_data += 1
            if data == "[DONE]":
                continue
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            ch = (obj.get("choices") or [{}])[0]
            if ch.get("finish_reason"):
                finish = ch["finish_reason"]
            piece = (ch.get("delta") or {}).get("content") or ""
            if piece and ttft is None:
                ttft = time.perf_counter() - t0
            if piece:
                pieces.append(piece)
    total = time.perf_counter() - t0
    return {
        "http": status,
        "ttft_s": ttft,
        "total_s": total,
        "decode_s": None if ttft is None else total - ttft,
        "text_chars": len("".join(pieces)),
        "text_head": "".join(pieces)[:120],
        "finish": finish,
        "sse_events": n_data,
    }


def server_progress(before: int) -> list[str]:
    try:
        data = ERR.read_bytes()[before:]
    except OSError:
        return []
    lines = []
    for line in data.decode("utf-8", "replace").splitlines():
        if "Prompt processing" in line or "Prompt Cache" in line or "Error" in line or "Traceback" in line:
            lines.append(line)
    return lines


def main() -> None:
    die_if_locked()
    OUT.mkdir(parents=True, exist_ok=True)
    tok = Tokenizer.from_file(str(ROOT / "tokenizer.json"))
    cases: list[tuple[str, str]] = []
    for n in (1024, 4096, 8192, 16384, 20000):
        cases.append((f"tokens-{n}", build_tokens(tok, n)))
    cjk = build_cjk(20000)
    cases.append(("cjk-chars-20000", cjk))
    # 32k only if the previous footprint stayed under the guard. Checked in loop.
    rows = []
    for name, content in cases:
        level = jetsam_level()
        fp = footprint_mb()
        if level is not None and level < 15:
            rows.append({"name": name, "skipped": f"jetsam {level}"})
            break
        if fp is not None and fp > 14000:
            rows.append({"name": name, "skipped": f"footprint {fp} MB"})
            break
        local_tokens = len(tok.encode(content).ids)
        local_chars = len(content)
        before = err_len()
        t_wall = time.perf_counter()
        try:
            rec = stream(content, max_tokens=16)
        except Exception as exc:  # noqa: BLE001
            rec = {"error": repr(exc)}
        rec.update(
            {
                "name": name,
                "local_tokens": local_tokens,
                "local_chars": local_chars,
                "footprint_before_mb": fp,
                "footprint_after_mb": footprint_mb(),
                "jetsam_before": level,
                "jetsam_after": jetsam_level(),
                "server_lines": server_progress(before),
                "wall_s": time.perf_counter() - t_wall,
            }
        )
        rows.append(rec)
        print(json.dumps({k: rec[k] for k in rec if k != "server_lines"}, ensure_ascii=False), flush=True)
        for line in rec["server_lines"]:
            print(" ", line, flush=True)
        after = rec.get("footprint_after_mb") or 0
        if after > 14000 or (rec.get("jetsam_after") is not None and rec["jetsam_after"] < 15):
            rows.append({"name": "stop", "reason": "memory guard", "footprint": after, "jetsam": rec.get("jetsam_after")})
            break
    stamp = time.strftime("%Y%m%dT%H%M%S")
    path = OUT / f"live-{stamp}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print("wrote", path)


if __name__ == "__main__":
    main()
