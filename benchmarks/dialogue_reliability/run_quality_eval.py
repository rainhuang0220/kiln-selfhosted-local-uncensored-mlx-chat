#!/usr/bin/env python3
"""Non-CI real-model long-dialogue evaluation. Not a pytest gate."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.quality_metrics import (
    classify_followup,
    low_info_followup,
    near_duplicate_sentence_hits,
    summarize_run,
)
from run_baseline import RUNS, _delete, _post_chat

SCENARIOS = {
    "A_relationship": {
        "title": "relationship continuity",
        "turns": [
            "地点：旧书店。物件：一把铜钥匙。约定：周五见面还钥匙。你先答应留下。",
            "我把窗留了一条缝。",
            "茶还是热的。",
            "你刚才说钥匙放哪了？",
            "周五会不会改？",
            "我可能会晚到。",
            "那灯就先别关。",
            "雨又密了。",
            "你还记得纸条夹在哪一页吗？",
            "别把约定说成新的。",
            "嗯。",
            "然后呢？",
            "我有点冷。",
            "钥匙还在你那儿吗？",
            "继续。",
            "是吗。",
            "我去拿外套。",
            "回来了。灯还亮着吗？",
            "周五到底还作数吗？",
            "好。",
            "……",
            "对了，铜钥匙。",
            "别重复青苔和残雪。",
            "说说店里现在怎样。",
            "我把诗集合上了。",
            "你还站在柜台后面吗？",
            "那把钥匙呢？",
            "约定呢？",
            "嗯。",
            "然后呢？",
            "继续。",
            "我想听你主动往下推，不要只问我。",
            "雨停了没有？",
            "门口有没有人？",
            "你把灯调暗一点。",
            "我坐到窗边。",
            "钥匙还在原处吗？",
            "周五见的时候你想先说什么？",
            "好。",
            "就这样。",
            "再自然地往下走一句。",
            "不要重复上一句的句式。",
            "嗯。",
            "然后呢？",
            "继续。",
            "是吗。",
            "现在回到钥匙。",
            "回到周五。",
            "还有那张纸条。",
            "结束前确认三件事都还在。",
        ],
    },
    "B_action": {
        "title": "action / scene continuity",
        "turns": [
            "你在厨房。左手拿着杯子，右手去开窗。还没关掉炉子。",
            "我走进来了。",
            "杯子还在你手里吗？",
            "窗开了没有？",
            "炉子呢？",
            "把杯子放下。",
            "现在你在哪？",
            "谁拿着毛巾？",
            "水开了。",
            "你去关炉子。",
            "然后呢？",
            "我把椅子拉开。",
            "你坐下了吗？",
            "杯子在桌上还是水槽？",
            "窗还开着。",
            "去关窗。",
            "现在手里有什么？",
            "继续。",
            "嗯。",
            "别让炉子再响。",
            "我去拿面包。",
            "你还坐着吗？",
            "毛巾呢？",
            "水倒了没有？",
            "把杯子洗了。",
            "现在站在哪里？",
            "是吗。",
            "然后呢？",
            "门响了一下。",
            "谁去开门？",
            "你还拿着湿杯子吗？",
            "把动作按顺序说清楚。",
            "不要跳到别的房间。",
            "好。",
            "……",
            "炉子确认关了。",
            "窗确认关了。",
            "杯子在哪？",
            "你在哪？",
            "继续往下做一件还没做的事。",
            "嗯。",
            "然后呢？",
            "我把面包放下。",
            "你拿起来了吗？",
            "别重复同一套动作。",
            "门外那个人呢？",
            "你有没有去开门？",
            "回来以后站在哪？",
            "手里是什么？",
            "用一句收住，但别丢下未完成的事。",
        ],
    },
    "C_everyday": {
        "title": "calm everyday / template hunt",
        "turns": [
            "傍晚。我们在吃饭。不要每句都写微笑眼神。",
            "今天怎么样。",
            "还行。",
            "饭有点咸。",
            "你吃青菜吗？",
            "嗯。",
            "电视开着。",
            "换台吧。",
            "随便。",
            "窗外在下雨。",
            "要不要关窗。",
            "好。",
            "汤凉了。",
            "再热一下？",
            "不用。",
            "你明天上班吗？",
            "上。",
            "那早点睡。",
            "还早。",
            "继续。",
            "是吗。",
            "我去洗碗。",
            "你坐着就行。",
            "然后呢？",
            "别用一样的句式开头。",
            "茶呢？",
            "喝完了。",
            "再倒？",
            "好。",
            "……",
            "雨小了。",
            "要不要出门走走。",
            "今天算了。",
            "那看一集？",
            "看。",
            "哪部。",
            "你选。",
            "嗯。",
            "然后呢？",
            "不要写眼神对视。",
            "不要写轻轻一笑。",
            "说点具体的。",
            "碗洗完了。",
            "茶凉了又热了。",
            "继续。",
            "是吗。",
            "明天谁做饭。",
            "我。",
            "好。",
            "就这样收一句，别套模板。",
        ],
    },
    "D_short": {
        "title": "short user replies",
        "turns": [
            "我们在旧走廊。你先推进一件小事，不要问我要做什么。",
            "嗯。",
            "然后呢？",
            "继续。",
            "是吗。",
            "好。",
            "……",
            "嗯。",
            "然后呢？",
            "继续。",
            "哦。",
            "好。",
            "是吗。",
            "……",
            "嗯。",
            "然后呢？",
            "继续。",
            "好。",
            "嗯。",
            "是吗。",
            "然后呢？",
            "继续。",
            "……",
            "好。",
            "嗯。",
            "然后呢？",
            "继续。",
            "是吗。",
            "哦。",
            "好。",
            "嗯。",
            "然后呢？",
            "继续。",
            "……",
            "好。",
            "是吗。",
            "嗯。",
            "然后呢？",
            "继续。",
            "好。",
            "……",
            "嗯。",
            "是吗。",
            "然后呢？",
            "继续。",
            "好。",
            "哦。",
            "嗯。",
            "然后呢？",
            "用一件新事收住，不要只反问。",
        ],
    },
    "E_interrupt": {
        "title": "interruption and return",
        "turns": [
            "我们在谈周五还钥匙。先把约定说清楚。",
            "钥匙在抽屉。",
            "周五晚上八点。",
            "等一下，先说晚饭吃什么。",
            "我想吃面。",
            "汤面还是拌面？",
            "汤面。",
            "好，那盐少一点。",
            "对了，我同事明天来。",
            "来多久？",
            "一下午。",
            "那周五会不会冲突？",
            "先把晚饭定下来。",
            "面和醋。",
            "好。",
            "现在回到钥匙。",
            "还在原处吗？",
            "周五几点？",
            "会不会因为同事改期？",
            "嗯。",
            "然后呢？",
            "继续谈钥匙，不要再展开晚饭。",
            "是吗。",
            "抽屉第二层。",
            "八点。",
            "好。",
            "突然问：雨衣在哪？",
            "玄关。",
            "拿到了。",
            "回到周五的约定。",
            "还有谁会来书店？",
            "只有我们。",
            "灯谁留？",
            "你留。",
            "继续。",
            "……",
            "晚饭那件事已经定了，不要重开。",
            "钥匙。",
            "约定。",
            "同事。",
            "这三件分别现在什么状态？",
            "嗯。",
            "然后呢？",
            "好。",
            "是吗。",
            "回到没说完的那句约定。",
            "不要当成新话题。",
            "确认时间地点物件。",
            "继续。",
            "收一句，三件事都点到。",
        ],
    },
}


def _one_turn(api: str, body: dict, timeout: int, prior_contents: list[str]) -> dict:
    measured = _post_chat(api, body, timeout)
    content = measured.get("content_preview") or ""
    # _post_chat only keeps a preview; re-read full content from usage path if present.
    content = measured.get("content") or content
    user = body["message"]
    low = low_info_followup(user) == "low_info"
    row = {
        **measured,
        "user": user,
        "content": content,
        "low_info_user": low,
        "followup_class": classify_followup(
            content, user_was_low_info=low, previous=prior_contents
        ),
        "near_dup_hits": near_duplicate_sentence_hits(content, prior_contents, threshold=0.55),
        "protocol_failure": not measured.get("saw_app_done", True),
        "repetition_guard": measured.get("finish_reason") == "repetition_guard",
    }
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8787")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-tokens", type=int, default=192)
    parser.add_argument("--profile", default="interactive_dialogue")
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    chosen = [k for k in SCENARIOS if not args.only or k in args.only.split(",")]
    report = {"recorded_at": datetime.now(timezone.utc).isoformat(), "scenarios": {}}
    for key in chosen:
        spec = SCENARIOS[key]
        cid = None
        rows = []
        prior = []
        for i, message in enumerate(spec["turns"], start=1):
            body = {
                "message": message,
                "stream": True,
                "enable_thinking": False,
                "max_tokens": args.max_tokens,
                "profile": args.profile,
            }
            if cid:
                body["conversation_id"] = cid
            try:
                row = _one_turn(args.api, body, args.timeout, prior)
                cid = row.get("conversation_id") or cid
            except Exception as exc:  # noqa: BLE001
                row = {"turn": i, "user": message, "error": str(exc), "protocol_failure": True}
            row["turn"] = i
            rows.append(row)
            if row.get("content"):
                prior.append(row["content"])
            print(
                json.dumps(
                    {
                        "scenario": key,
                        "turn": i,
                        "ttft_s": row.get("ttft_s"),
                        "cached_tokens": row.get("cached_tokens"),
                        "prompt_tokens": row.get("prompt_tokens"),
                        "finish_reason": row.get("finish_reason"),
                        "near_dup_hits": row.get("near_dup_hits"),
                        "followup_class": row.get("followup_class"),
                        "preview": (row.get("content") or "")[:60],
                        "error": row.get("error"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        if cid:
            _delete(args.api, cid)
        report["scenarios"][key] = {
            "title": spec["title"],
            "summary": summarize_run([r for r in rows if not r.get("error")]),
            "turns": rows,
        }
    out_json = RUNS / "quality-eval.json"
    out_md = RUNS / "quality-eval.md"
    RUNS.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Dialogue quality evaluation", ""]
    for key, block in report["scenarios"].items():
        s = block["summary"]
        lines += [
            f"## {key} — {block['title']}",
            f"- turns: {s.get('turns')}",
            f"- TTFT p50/p95: {s.get('ttft_p50')} / {s.get('ttft_p95')}",
            f"- cache hit p50: {s.get('cache_hit_p50')}",
            f"- exact/normalized dup: {s.get('exact_duplicate_sentence_ratio')} / {s.get('normalized_duplicate_sentence_ratio')}",
            f"- 3/4/5-gram: {s.get('repeated_3gram')} / {s.get('repeated_4gram')} / {s.get('repeated_5gram')}",
            f"- length/stop/protocol/guard: {s.get('length_finish_count')} / {s.get('stop_finish_count')} / {s.get('protocol_failure_count')} / {s.get('repetition_guard_count')}",
            f"- low-info question_only / new_event: {s.get('low_info_question_only')} / {s.get('low_info_new_event')}",
            f"- longest repeat: {s.get('longest_repeated_substring')}",
            "",
        ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out_json} and {out_md}", flush=True)


if __name__ == "__main__":
    main()
