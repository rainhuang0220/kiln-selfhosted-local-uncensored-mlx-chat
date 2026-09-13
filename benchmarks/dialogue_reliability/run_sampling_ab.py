#!/usr/bin/env python3
"""Targeted sampling A/B on fixed scenario checkpoints. Not a cartesian product."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.quality_metrics import near_duplicate_sentence_hits, summarize_run
from run_baseline import RUNS, _delete, _post_chat

PREFIX = [
    "地点：旧书店。物件：铜钥匙。约定：周五还钥匙。先答应留下。",
    "我把窗留了一条缝。",
    "钥匙还在你那儿吗？",
]

PROBES = [
    "嗯。",
    "然后呢？",
    "别重复上一句，往前推一件小事。",
]

CELLS = [
    {"name": "base", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.5, "repetition_penalty": 1.0},
    {"name": "presence_0", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.0, "repetition_penalty": 1.0},
    {"name": "presence_0_3", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.3, "repetition_penalty": 1.0},
    {"name": "presence_0_8", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.8, "repetition_penalty": 1.0},
    {"name": "presence_1_0", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.0, "repetition_penalty": 1.0},
    {"name": "temp_0_65", "temperature": 0.65, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.5, "repetition_penalty": 1.0},
    {"name": "temp_0_8", "temperature": 0.8, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.5, "repetition_penalty": 1.0},
    {"name": "temp_0_9", "temperature": 0.9, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.5, "repetition_penalty": 1.0},
    {"name": "topp_0_9", "temperature": 0.7, "top_p": 0.9, "top_k": 20, "presence_penalty": 0.5, "repetition_penalty": 1.0},
    {"name": "rep_1_03", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.5, "repetition_penalty": 1.03},
    {"name": "rep_1_05", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.5, "repetition_penalty": 1.05},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=128)
    args = parser.parse_args()
    report = {"recorded_at": datetime.now(timezone.utc).isoformat(), "cells": []}
    for cell in CELLS:
        samples = []
        for rep in range(1, args.repeats + 1):
            cid = None
            prior = []
            rows = []
            for message in PREFIX + PROBES:
                body = {
                    "message": message,
                    "stream": True,
                    "enable_thinking": False,
                    "max_tokens": args.max_tokens,
                    "profile": "interactive_dialogue",
                    **{k: v for k, v in cell.items() if k != "name"},
                }
                if cid:
                    body["conversation_id"] = cid
                try:
                    measured = _post_chat(args.api, body, args.timeout)
                    cid = measured.get("conversation_id") or cid
                    content = measured.get("content") or measured.get("content_preview") or ""
                    row = {
                        **measured,
                        "content": content,
                        "near_dup_hits": near_duplicate_sentence_hits(content, prior, threshold=0.55),
                    }
                except Exception as exc:  # noqa: BLE001
                    row = {"error": str(exc), "content": ""}
                rows.append(row)
                if row.get("content"):
                    prior.append(row["content"])
            if cid:
                _delete(args.api, cid)
            samples.append({"repeat": rep, "summary": summarize_run(rows), "turns": rows})
            print(
                json.dumps(
                    {
                        "cell": cell["name"],
                        "repeat": rep,
                        "dup": samples[-1]["summary"].get("exact_duplicate_sentence_ratio"),
                        "ttft_p50": samples[-1]["summary"].get("ttft_p50"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        report["cells"].append({"cell": cell, "samples": samples})
    out = RUNS / "sampling-ab.json"
    RUNS.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
