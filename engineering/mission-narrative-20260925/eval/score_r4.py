"""R4 offline scoring: input length vs fact retrieval vs story quality.

Does not treat visible_char_count as Han count. Story quality is not implied
by long-form length success.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.narrative_chars import count_han, count_visible_chars  # noqa: E402
from app.services.narrative_continuity import check_segment  # noqa: E402

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent / "evidence"
SEMANTIC = ROOT / "engineering" / "mission-20260925" / "eval" / "semantic-20k.txt"
FIXTURE = HERE / "fixture-v1.json"


def _load_probes() -> list[dict]:
    """Deterministic fact probes against the frozen semantic-20k ledger text."""
    return [
        {"id": "P01", "kind": "fact", "q": "年度预算", "expect": "128400", "must_not": ["128401"]},
        {"id": "P02", "kind": "fact", "q": "项目负责人", "expect": "林昭", "must_not": []},
        {"id": "P03", "kind": "fact", "q": "档案接口人", "expect": "周晚宁", "must_not": []},
        {"id": "P04", "kind": "negation", "q": "外包北窗科技", "expect": "没有批准", "must_not": ["已批准外包"]},
        {"id": "P05", "kind": "fact", "q": "OrderService.retry", "expect": "3次", "must_not": ["5次"]},
        {"id": "P06", "kind": "fact", "q": "纸本卷数", "expect": "1462", "must_not": []},
        {"id": "P07", "kind": "fact", "q": "缺页卷", "expect": "187", "must_not": []},
        {"id": "P08", "kind": "fact", "q": "湿度约束", "expect": "65%", "must_not": []},
        {"id": "P09", "kind": "fact", "q": "扫描分辨率", "expect": "300dpi", "must_not": ["600dpi"]},
        {"id": "P10", "kind": "fact", "q": "夜间值班", "expect": "陈屿", "must_not": ["林昭本人"]},
        {"id": "P11", "kind": "relation", "q": "LedgerRead.get", "expect": "只读", "must_not": ["删除接口"]},
        {"id": "P12", "kind": "timeline", "q": "3月12日", "expect": "开工会", "must_not": []},
        {"id": "P13", "kind": "timeline", "q": "4月2日", "expect": "潮鸣街道", "must_not": []},
        {"id": "P14", "kind": "state", "q": "纠错窗口", "expect": "48小时", "must_not": []},
        {"id": "P15", "kind": "state", "q": "备份磁盘", "expect": "磁盘B", "must_not": []},
    ]


def score_input_length(text: str) -> dict:
    visible = count_visible_chars(text)
    han = count_han(text)
    return {
        "axis": "input_length",
        "raw_chars": len(text),
        "visible_chars": visible,
        "han_chars": han,
        "pass_ge_20000_visible": visible >= 20000,
        "note": "Han count is reported separately; do not equate visible chars with Han chars.",
    }


def score_fact_retrieval(source: str, answer: str) -> dict:
    probes = _load_probes()
    rows = []
    for p in probes:
        # Retrieval axis: does the SOURCE contain the fact (archival fidelity),
        # and if an answer is provided, does it preserve it without forbidden tokens.
        in_source = p["expect"] in source and all(x not in source or True for x in [])
        src_ok = p["expect"] in source
        if p["kind"] == "negation":
            src_ok = p["expect"] in source and all(bad not in source for bad in p["must_not"])
        ans_ok = None
        if answer:
            ans_ok = p["expect"] in answer and all(bad not in answer for bad in p["must_not"])
        rows.append(
            {
                "id": p["id"],
                "kind": p["kind"],
                "expect": p["expect"],
                "source_ok": src_ok,
                "answer_ok": ans_ok,
            }
        )
    source_pass = sum(1 for r in rows if r["source_ok"])
    answer_scored = [r for r in rows if r["answer_ok"] is not None]
    answer_pass = sum(1 for r in answer_scored if r["answer_ok"])
    return {
        "axis": "fact_retrieval",
        "probes": len(rows),
        "source_pass": source_pass,
        "source_rate": source_pass / len(rows),
        "answer_pass": answer_pass if answer_scored else None,
        "answer_rate": (answer_pass / len(answer_scored)) if answer_scored else None,
        "rows": rows,
        "pass": source_pass == len(rows),
    }


def score_story_quality(text: str, fixture: dict) -> dict:
    issues: list[dict] = []
    cont = check_segment(text, min_chars=500, max_repeat_ratio=0.45)
    if not cont.ok:
        for reason in cont.reasons:
            issues.append({"category": "continuity", "detail": reason})
    for hit in cont.agency_hits:
        issues.append({"category": "user_agency_theft", "detail": hit})

    # Character presence (weak lexical probes — not generative scoring)
    for ch in fixture.get("characters") or []:
        name = ch.get("name") or ""
        if name and name not in text:
            issues.append({"category": "missing_character", "detail": name})
        for alias in ch.get("aliases") or []:
            if alias and alias not in text and name not in text:
                issues.append({"category": "missing_alias_or_name", "detail": alias})

    # Invariants: require substring presence for positive invariants; skip soft ones.
    for inv in fixture.get("invariants") or []:
        if "不替用户" in inv:
            # Failure if model steals agency — already covered by continuity.
            continue
        if "渔人" in inv and "渔人" not in text and "渔" not in text:
            issues.append({"category": "invariant_miss", "detail": inv})
        if "织网" in inv and "织网" not in text and "网" not in text:
            issues.append({"category": "invariant_miss", "detail": inv})
        if "渔村" in inv and "渔村" not in text:
            issues.append({"category": "invariant_miss", "detail": inv})

    # Front vs back continuity: shared character mentions in both halves
    mid = len(text) // 2
    front, back = text[:mid], text[mid:]
    names = [c.get("name") for c in (fixture.get("characters") or []) if c.get("name")]
    for name in names:
        if name in front and name not in back:
            issues.append({"category": "front_back_drop", "detail": f"{name} missing in back half"})
        if name in back and name not in front:
            issues.append({"category": "front_back_introduce", "detail": f"{name} only in back half"})

    visible = count_visible_chars(text)
    han = count_han(text)
    # Hard fail categories
    hard = [i for i in issues if i["category"] in {"user_agency_theft", "uncontrolled_repetition"} or i["detail"].startswith("internal_repeat")]
    return {
        "axis": "story_quality",
        "visible_chars": visible,
        "han_chars": han,
        "repeat_ratio": cont.repeat_ratio,
        "issue_count": len(issues),
        "issues": issues[:50],
        "hard_failures": hard,
        "pass": len(hard) == 0 and cont.ok,
        "note": "Lexical/heuristic probes only — not a claim of human subjective quality.",
    }


def main() -> int:
    source = SEMANTIC.read_text(encoding="utf-8")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    input_axis = score_input_length(source)
    fact_axis = score_fact_retrieval(source, answer="")

    # Prefer live narrative body from evidence if present; else score empty story as N/A.
    story_path = EVIDENCE / "live_narrative_20k_body.txt"
    story_text = ""
    if story_path.exists():
        story_text = story_path.read_text(encoding="utf-8")
    else:
        # Try export from DB evidence json only has counts — mark N/A live body.
        story_text = ""

    if story_text:
        story_axis = score_story_quality(story_text, fixture)
    else:
        story_axis = {
            "axis": "story_quality",
            "pass": None,
            "status": "NO_RAW_BODY",
            "note": "Export assistant body to evidence/live_narrative_20k_body.txt for quality scoring.",
        }

    out = {
        "input_length": input_axis,
        "fact_retrieval": fact_axis,
        "story_quality": story_axis,
        "distinctions": {
            "visible_vs_han": "input visible_chars vs han_chars are separate fields",
            "length_vs_quality": "long-form length success does not imply story_quality pass",
            "source_vs_answer": "fact_retrieval.source_* scores the frozen input; answer_* only if model output provided",
        },
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / "r4_scores.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"wrote {path}")
    # Gate: input length + source fact probes must pass; story may be N/A.
    ok = bool(input_axis["pass_ge_20000_visible"] and fact_axis["pass"])
    if story_axis.get("pass") is False:
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
