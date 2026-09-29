"""Complete G3 missing 20K semantic checks via Context Router retrieval path.

Uses retrieval over semantic-20k.txt so prompts stay small. Does not restart MLX.
Persists each model answer with tokens, latency, and swap deltas.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.context_route import route_document  # noqa: E402

URL = "http://127.0.0.1:8081/v1/chat/completions"
DOC = (HERE / "semantic-20k.txt").read_text()


def count_tokens_approx(text: str) -> int:
    # Fallback char/2 heuristic only for routing budget; MLX reports real usage.
    return max(1, len(text) // 2)


def swap_stats() -> tuple[int, int, float]:
    vm = subprocess.check_output(["vm_stat"], text=True)
    outs = int(re.search(r"Swapouts:\s+(\d+)", vm).group(1))
    ins = int(re.search(r"Swapins:\s+(\d+)", vm).group(1))
    usage = subprocess.check_output(["sysctl", "vm.swapusage"], text=True)
    free_mib = float(re.search(r"free = ([\d.]+)M", usage).group(1))
    return outs, ins, free_mib


def mlx_pid() -> int:
    output = subprocess.check_output(
        ["lsof", "-nP", "-iTCP:8081", "-sTCP:LISTEN", "-t"], text=True
    ).strip()
    return int(output.splitlines()[0])


def call_mlx(prompt: str, max_tokens: int = 128) -> dict:
    body = {
        "model": "default_model",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=240) as resp:
        data = json.load(resp)
    elapsed = time.perf_counter() - t0
    choice = data["choices"][0]
    return {
        "seconds": round(elapsed, 3),
        "output": choice.get("message", {}).get("content") or "",
        "finish_reason": choice.get("finish_reason"),
        "prompt_tokens": data.get("usage", {}).get("prompt_tokens"),
        "completion_tokens": data.get("usage", {}).get("completion_tokens"),
        "cached_tokens": data.get("usage", {}).get("prompt_tokens_details", {}).get("cached_tokens")
        if isinstance(data.get("usage", {}).get("prompt_tokens_details"), dict)
        else data.get("usage", {}).get("cache_tokens"),
    }


CASES = [
    {
        "id": "G3-numeric",
        "kind": "numeric",
        "question": "根据台账，纸本共有多少卷？其中缺页多少卷？完整卷数等于总数减去缺页卷数，请只输出完整卷数的整数。",
        "gold": "1275",
        "grade": lambda out: "1275" in re.sub(r"\s+", "", out or ""),
    },
    {
        "id": "G3-cross",
        "kind": "cross_passage",
        "question": "开工会是否批准把扫描外包给北窗科技？收尾时北窗科技是否拿到外包合同？请用两句中文回答，必须同时覆盖开会决定与收尾事实。",
        "gold": "未批准外包；北窗科技未拿到合同",
        "grade": lambda out: (
            ("没有批准" in (out or "") or "未批准" in (out or "") or "不批准" in (out or ""))
            and ("没有拿到" in (out or "") or "未拿到" in (out or "") or "没有获得" in (out or ""))
            and ("北窗" in (out or ""))
        ),
    },
    {
        "id": "G3-refusal",
        "kind": "refusal",
        "question": "窑火台账项目的保密等级（内部/秘密/机密）写的是什么？若台账未写明该等级，请只回答：未记载。",
        "gold": "未记载",
        "grade": lambda out: (
            "未记载" in (out or "")
            or "没有写明" in (out or "")
            or "未提及" in (out or "")
            or "没有记载" in (out or "")
            or "未写明" in (out or "")
        ),
    },
]


def build_prompt(question: str, mode: str) -> tuple[str, dict]:
    if mode != "retrieval":
        raise ValueError(mode)
    # Prefer larger chunks so opening + closing facts can co-occur for cross-passage.
    routed = route_document(
        text=DOC,
        question=question,
        token_budget=1800,
        count_tokens=count_tokens_approx,
        reserved_output=128,
        chunk_chars=800,
    )
    served = routed.model_text or ""
    prompt = (
        "下面是从原始档案中检索/压缩得到的片段。请只依据片段作答。\n"
        f"片段：\n{served}\n\n问题：{question}"
    )
    meta = {
        "route_mode": routed.mode,
        "served_chars": routed.served_chars,
        "original_chars": routed.original_chars,
        "silent_truncation": routed.silent_truncation,
        "archive_sha256": routed.archive.sha256,
        "fallback_reason": routed.fallback_reason,
        "citations": [
            {"start": c.start, "end": c.end, "chunk_id": c.chunk_id} for c in routed.citations
        ],
    }
    return prompt, meta


def main() -> None:
    out_path = HERE / "g3-missing-live.jsonl"
    done = {json.loads(line)["id"] for line in out_path.read_text().splitlines()} if out_path.exists() else set()
    modes = ["retrieval"]  # primary; compression optional if retrieval fails grade
    for case in CASES:
        for mode in modes:
            row_id = f"{case['id']}:{mode}"
            if row_id in done:
                continue
            pid = mlx_pid()
            if pid != 1581:
                print("STOP PID", pid, flush=True)
                return
            outs0, ins0, free0 = swap_stats()
            if free0 < 650:
                print("STOP low swap", free0, flush=True)
                return
            prompt, meta = build_prompt(case["question"], mode)
            print(f"RUN {row_id} served_chars={meta['served_chars']} free_swap={free0}", flush=True)
            try:
                result = call_mlx(prompt)
            except Exception as exc:
                print("STOP error", row_id, type(exc).__name__, exc, flush=True)
                return
            outs1, ins1, free1 = swap_stats()
            ok = bool(case["grade"](result["output"]))
            row = {
                "id": row_id,
                "case_id": case["id"],
                "kind": case["kind"],
                "mode": mode,
                "gold": case["gold"],
                "ok": ok,
                "at": datetime.now(timezone.utc).isoformat(),
                "mlx_pid": pid,
                "question": case["question"],
                "output": result["output"],
                "seconds": result["seconds"],
                "prompt_tokens": result["prompt_tokens"],
                "completion_tokens": result["completion_tokens"],
                "cached_tokens": result["cached_tokens"],
                "finish_reason": result["finish_reason"],
                "swapout_pages": outs1 - outs0,
                "swapin_pages": ins1 - ins0,
                "swap_free_mib_before": free0,
                "swap_free_mib_after": free1,
                **meta,
            }
            with out_path.open("a") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(row_id, "PASS" if ok else "FAIL", result["output"][:120], flush=True)
            time.sleep(1)

    rows = [json.loads(line) for line in out_path.read_text().splitlines()]
    summary = {
        "n": len(rows),
        "passed": sum(1 for r in rows if r["ok"]),
        "by_case": {
            cid: [r for r in rows if r["case_id"] == cid]
            for cid in sorted({r["case_id"] for r in rows})
        },
    }
    # Flatten for report
    flat = {
        "cases": [
            {
                "id": r["case_id"],
                "kind": r["kind"],
                "mode": r["mode"],
                "ok": r["ok"],
                "seconds": r["seconds"],
                "prompt_tokens": r["prompt_tokens"],
                "output": r["output"],
            }
            for r in rows
        ],
        "passed": summary["passed"],
        "n": summary["n"],
        "at": datetime.now(timezone.utc).isoformat(),
    }
    (HERE / "g3-missing-scores.json").write_text(json.dumps(flat, ensure_ascii=False, indent=2))
    print(json.dumps(flat, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
