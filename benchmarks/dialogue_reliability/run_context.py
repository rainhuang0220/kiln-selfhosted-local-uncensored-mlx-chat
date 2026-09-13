#!/usr/bin/env python3
"""Cold prompt sizes and warm multi-turn TTFT. Does not retune MLX flags."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import RUNS, _delete, _post_chat  # type: ignore

SEED = "雨停了。门口还亮着一盏灯。"


def _pad(target_chars: int) -> str:
    block = "旧书店的灯还亮着，钥匙还在原处，约定没有改。 "
    return "[kiln-bench] " + SEED + " " + (block * (1 + target_chars // len(block)))[:target_chars]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-cold", type=int, default=32000)
    parser.add_argument("--warm-turns", type=int, default=20)
    args = parser.parse_args()
    cold_sizes = [n for n in (100, 1000, 4000, 8000, 16000, 32000) if n <= args.max_cold]
    rows: list[dict] = []
    for size in cold_sizes:
        body = {
            "message": _pad(size * 2),
            "stream": True,
            "enable_thinking": False,
            "max_tokens": 32,
            "profile": "interactive_dialogue",
        }
        row = {"kind": "cold", "target_prompt_chars": size * 2}
        try:
            measured = _post_chat(args.api, body, args.timeout)
            row.update(measured)
            if measured.get("conversation_id"):
                _delete(args.api, measured["conversation_id"])
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    cid = None
    for turn in range(1, args.warm_turns + 1):
        body = {
            "message": f"[kiln-bench] turn {turn}。{SEED} 请只回一句，不要重复上一句。",
            "stream": True,
            "enable_thinking": False,
            "max_tokens": 48,
            "profile": "interactive_dialogue",
        }
        if cid:
            body["conversation_id"] = cid
        row = {"kind": "warm", "turn": turn}
        try:
            measured = _post_chat(args.api, body, args.timeout)
            row.update(measured)
            cid = measured.get("conversation_id") or cid
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    if cid:
        _delete(args.api, cid)

    out = RUNS / "context-cold-warm.json"
    RUNS.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"recorded_at": datetime.now(timezone.utc).isoformat(), "results": rows},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
