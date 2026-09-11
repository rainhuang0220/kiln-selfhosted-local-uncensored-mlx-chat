#!/usr/bin/env python3
"""Post-process quality-eval.json into RC2 tables and worst cases."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.quality_metrics import classify_followup, low_info_followup, summarize_run
from run_baseline import RUNS


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((p / 100) * (len(ordered) - 1))))
    return float(ordered[idx])


def main() -> None:
    src = RUNS / "quality-eval.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    all_rows: list[dict] = []
    worst: list[dict] = []
    lines = ["# RC2 real-model dialogue evaluation", ""]
    for key, block in data.get("scenarios", {}).items():
        rows = [r for r in block.get("turns") or [] if not r.get("error")]
        prior: list[str] = []
        for row in rows:
            user = str(row.get("user") or "")
            content = str(row.get("content") or "")
            low = low_info_followup(user) == "low_info"
            row["low_info_user"] = low
            row["followup_class"] = classify_followup(
                content, user_was_low_info=low, previous=prior
            )
            if content:
                prior.append(content)
        block["summary"] = summarize_run(rows)
        all_rows.extend({**r, "scenario": key} for r in rows)
        s = block.get("summary") or {}
        lines += [
            f"## {key} — {block.get('title')}",
            f"- turns: {s.get('turns')}",
            f"- TTFT p50/p95: {s.get('ttft_p50')} / {s.get('ttft_p95')}",
            f"- decode tok/s p50: {s.get('decode_tok_s_p50')}",
            f"- cache hit p50: {s.get('cache_hit_p50')}",
            f"- exact/normalized dup: {s.get('exact_duplicate_sentence_ratio')} / {s.get('normalized_duplicate_sentence_ratio')}",
            f"- 3/4/5-gram: {s.get('repeated_3gram')} / {s.get('repeated_4gram')} / {s.get('repeated_5gram')}",
            f"- paragraph near-dup: {s.get('paragraph_near_duplicate_ratio')}",
            f"- opening/closing diversity: {s.get('opening_diversity')} / {s.get('closing_diversity')}",
            f"- length/stop/protocol/guard: {s.get('length_finish_count')} / {s.get('stop_finish_count')} / {s.get('protocol_failure_count')} / {s.get('repetition_guard_count')}",
            f"- low-info question_only / new_event / repeat: {s.get('low_info_question_only')} / {s.get('low_info_new_event')} / {s.get('low_info_repeat')}",
            "",
        ]
        for row in rows:
            score = 0
            score += 3 * int(row.get("near_dup_hits") or 0)
            score += 4 if row.get("followup_class") == "question_only" else 0
            score += 5 if row.get("protocol_failure") else 0
            score += 5 if row.get("repetition_guard") else 0
            score += 2 if row.get("finish_reason") == "length" else 0
            if score:
                worst.append({"score": score, "scenario": key, **row})
    worst.sort(key=lambda r: r["score"], reverse=True)
    lines += ["## Worst observed turns", ""]
    for row in worst[:5]:
        lines.append(
            f"- **{row['scenario']} turn {row.get('turn')}** score={row['score']} "
            f"class={row.get('followup_class')} dups={row.get('near_dup_hits')} "
            f"finish={row.get('finish_reason')}"
        )
        lines.append(f"  - user: {row.get('user')}")
        lines.append(f"  - assistant: {(row.get('content') or '')[:280]}")
        lines.append("")
    ttfts = [float(r["ttft_s"]) for r in all_rows if r.get("ttft_s") is not None]
    decodes = [float(r["decode_tok_s"]) for r in all_rows if r.get("decode_tok_s")]
    eff = [float(r["effective_output_tok_s"]) for r in all_rows if r.get("effective_output_tok_s")]
    hits = []
    prompts = []
    for r in all_rows:
        p = float(r.get("prompt_tokens") or 0)
        c = float(r.get("cached_tokens") or 0)
        prompts.append(p)
        hits.append((c / p) if p else 0.0)
    buckets = {"4k": [], "6k": [], "8k": [], "10k": [], "12k": [], "16k": []}
    for r in all_rows:
        p = float(r.get("prompt_tokens") or 0)
        t = r.get("ttft_s")
        if t is None:
            continue
        if p < 5000:
            buckets["4k"].append(float(t))
        elif p < 7000:
            buckets["6k"].append(float(t))
        elif p < 9000:
            buckets["8k"].append(float(t))
        elif p < 11000:
            buckets["10k"].append(float(t))
        elif p < 14000:
            buckets["12k"].append(float(t))
        else:
            buckets["16k"].append(float(t))
    overall = {
        "turns": len(all_rows),
        "ttft_p50": _pct(ttfts, 50),
        "ttft_p95": _pct(ttfts, 95),
        "decode_tok_s_p50": _pct(decodes, 50),
        "effective_tok_s_p50": _pct(eff, 50),
        "cache_hit_p50": _pct(hits, 50),
        "prompt_tokens_p50": _pct(prompts, 50),
        "prompt_tokens_p95": _pct(prompts, 95),
        "protocol_failures": sum(1 for r in all_rows if r.get("protocol_failure") or r.get("error")),
        "warm_ttft_by_prompt_bucket": {
            k: {"n": len(v), "p50": _pct(v, 50), "p95": _pct(v, 95)} for k, v in buckets.items()
        },
    }
    lines += ["## Overall", json.dumps(overall, ensure_ascii=False, indent=2), ""]
    out_md = RUNS / "quality-eval.md"
    out_md.write_text("\n".join(lines), encoding="utf-8")
    (RUNS / "quality-eval-overall.json").write_text(
        json.dumps({"overall": overall, "worst": worst[:5]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(overall, ensure_ascii=False, indent=2))
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()
