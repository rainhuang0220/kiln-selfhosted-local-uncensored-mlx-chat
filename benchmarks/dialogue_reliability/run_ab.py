#!/usr/bin/env python3
"""Targeted sampling A/B. Not a cartesian product. Deletes bench conversations."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import RUNS, _delete, _post_chat  # type: ignore

PROMPT = "[kiln-bench] 深夜书房。用户说：钥匙还在你那儿吗？用自然中文推进互动，不要重复同一句。"

CELLS = [
    {"name": "official_non_thinking", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "max_tokens": 256},
    {"name": "warmer_topp", "temperature": 0.8, "top_p": 0.9, "top_k": 20, "max_tokens": 256},
    {"name": "wider_topk", "temperature": 0.7, "top_p": 0.8, "top_k": 40, "max_tokens": 256},
    {"name": "presence_0", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.0, "max_tokens": 256},
    {"name": "presence_0_5", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.5, "max_tokens": 256},
    {"name": "presence_1_0", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.0, "max_tokens": 256},
    {"name": "presence_1_5", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5, "max_tokens": 256},
    {"name": "rep_1_05", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "repetition_penalty": 1.05, "max_tokens": 256},
    {"name": "rep_1_08", "temperature": 0.7, "top_p": 0.8, "top_k": 20, "repetition_penalty": 1.08, "max_tokens": 256},
]


def main() -> None:
    api = "http://127.0.0.1:8787"
    rows = []
    for cell in CELLS:
        body = {
            "message": PROMPT,
            "stream": True,
            "enable_thinking": False,
            "profile": "interactive_dialogue",
            "temperature": cell["temperature"],
            "top_p": cell["top_p"],
            "top_k": cell["top_k"],
            "max_tokens": cell["max_tokens"],
        }
        if "presence_penalty" in cell:
            body["presence_penalty"] = cell["presence_penalty"]
        if "repetition_penalty" in cell:
            body["repetition_penalty"] = cell["repetition_penalty"]
        row = {"name": cell["name"], **cell}
        try:
            measured = _post_chat(api, body, 180)
            row.update(measured)
            if measured.get("conversation_id"):
                _delete(api, measured["conversation_id"])
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    out = RUNS / "ab-targeted.json"
    RUNS.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"results": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
