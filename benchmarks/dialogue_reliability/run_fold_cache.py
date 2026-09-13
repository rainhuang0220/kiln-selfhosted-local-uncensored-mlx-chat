#!/usr/bin/env python3
"""Isolate rolling-fold cache loss from mlx-lm kwargs behavior.

Uses a fixed transcript and three prompt builders. Talks to mlx-lm directly.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.dialogue_checkpoints import build_immutable_context
from app.services.dialogue_context import build_dialogue_context
from run_prompt_cache import RUNS, post_mlx

SYSTEM = "你是简短中文对话伙伴。只回一句。"


def transcript(n: int) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM}]
    facts = [
        "地点：旧书店。约定：周五还钥匙。物件：铜钥匙还在抽屉。",
        "我把灯留下了。",
        "门没有锁。",
        "桌上还有没喝完的茶。",
        "钥匙还在你那儿吗？",
        "今晚能还我吗？",
        "大概几点？",
        "到时发我一下。",
        "雨又开始了。",
        "要不要把窗关上？",
        "茶凉了。",
        "那本诗集还在原处。",
        "你刚才说周五。",
        "我可能会晚一点。",
        "灯还亮着吗？",
        "别重复上一句。",
        "嗯。",
        "然后呢？",
        "继续。",
        "是吗。",
        "对了，钥匙呢？",
        "书店的灯呢？",
        "周五的约定还作数吗？",
        "好。",
        "……",
    ]
    replies = [
        "灯还亮着，钥匙在抽屉第二层。",
        "我知道，窗还开着一条缝。",
        "我没动它。",
        "茶渍已经干了。",
        "还在，没带出门。",
        "可以，我下班带回。",
        "大概八点。",
        "好，放到门口就发你。",
        "我去关窗。",
        "已经关上了。",
        "我重新烧一壶。",
        "诗集还夹着你的纸条。",
        "周五没改。",
        "那我在店里等。",
        "亮着，没熄。",
        "窗缝里还有一点雨味。",
        "茶开了。",
        "纸条还在目录页。",
        "我把钥匙放到柜台。",
        "约定还在。",
        "抽屉里，和第一天一样。",
        "还亮，只是暗了一档。",
        "作数。",
        "那我八点前来。",
        "我在门口留灯。",
    ]
    for i in range(n):
        msgs.append({"role": "user", "content": facts[i % len(facts)]})
        msgs.append({"role": "assistant", "content": replies[i % len(replies)]})
    return msgs


def _estimate(text: str) -> int:
    return max(1, len(text or "") // 2)


def build_messages(kind: str, history: list[dict], budget: int) -> list[dict]:
    if kind == "control":
        return history
    if kind == "fold-current":
        built = build_dialogue_context(
            history,
            budget=budget,
            estimate=_estimate,
            recent_turn_target=8,
            fold_every_turns=4,
            min_recent_turns=4,
        )
        return built.messages
    built = build_immutable_context(
        history,
        budget=budget,
        estimate=_estimate,
        recent_turn_target=8,
        fold_every_turns=4,
        min_recent_turns=4,
        max_checkpoints=3,
    )
    return built.messages


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8081")
    parser.add_argument("--turns", type=int, default=20)
    parser.add_argument("--budget", type=int, default=4000)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--kinds", default="control,fold-current,fold-immutable")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    full = transcript(args.turns)
    rows = []
    for kind in [k.strip() for k in args.kinds.split(",") if k.strip()]:
        for turn in range(1, args.turns + 1):
            history = full[: 1 + turn * 2]
            # Ask the next user turn so the model has a generation prompt.
            if turn < args.turns:
                nxt = full[1 + turn * 2]
                messages = build_messages(kind, history, args.budget) + [nxt]
            else:
                messages = build_messages(kind, history, args.budget) + [
                    {"role": "user", "content": "只回一句，不要重复。"}
                ]
            row = {
                "kind": kind,
                "turn": turn,
                "n_messages": len(messages),
                "prompt_chars": sum(len(m.get("content") or "") for m in messages),
            }
            try:
                measured = post_mlx(
                    args.api,
                    messages,
                    stream=True,
                    kwargs={"enable_thinking": False},
                    max_tokens=16,
                    timeout=args.timeout,
                )
                row.update(measured)
            except Exception as exc:  # noqa: BLE001
                row["error"] = str(exc)
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in (
                "kind", "turn", "n_messages", "prompt_tokens", "cached_tokens",
                "cache_ratio", "ttft_s", "total_s", "error"
            )}, ensure_ascii=False), flush=True)
    out = Path(args.out) if args.out else RUNS / "fold-cache.json"
    RUNS.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"recorded_at": datetime.now(timezone.utc).isoformat(), "results": rows},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
