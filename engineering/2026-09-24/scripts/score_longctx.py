#!/usr/bin/env python3
"""Score offline long-context predictions. No network.

Cases JSONL fields: id, category, input, question, gold, scoring_rule, tags,
generator_note. Predictions JSONL: {"id", "output"}.

exact: full string after NFKC and whitespace collapse. Case is significant.
contains_all / ordered: same normalization, then bounded spans (ASCII word
characters and CJK characters do not match inside a longer token).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

RULES = ("exact", "contains_all", "ordered")
REQUIRED = (
    "id",
    "category",
    "input",
    "question",
    "gold",
    "scoring_rule",
    "tags",
    "generator_note",
)

DEFAULT_CASES = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "longctx" / "cases.jsonl"
)


def die(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = text.replace("\u3000", " ")
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _ascii_word(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def _cjk(ch: str) -> bool:
    o = ord(ch)
    return (
        0x3400 <= o <= 0x4DBF
        or 0x4E00 <= o <= 0x9FFF
        or 0xF900 <= o <= 0xFAFF
    )


def _glued(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return (_ascii_word(left) and _ascii_word(right)) or (_cjk(left) and _cjk(right))


def find_bounded(text: str, needle: str, start: int = 0) -> int:
    if not needle:
        return -1
    i = start
    while True:
        j = text.find(needle, i)
        if j < 0:
            return -1
        end = j + len(needle)
        prev = text[j - 1] if j else ""
        nxt = text[end] if end < len(text) else ""
        if _glued(prev, needle[0]) or _glued(needle[-1], nxt):
            i = j + 1
            continue
        return j


def _items(gold) -> list[str]:
    if not isinstance(gold, list) or not gold:
        raise ValueError("contains_all and ordered require a non-empty gold list")
    out = []
    for item in gold:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("gold list items must be non-empty strings")
        out.append(normalize(item))
    return out


def passes(rule: str, gold, output: str) -> bool:
    text = normalize(output)
    if rule == "exact":
        if not isinstance(gold, str):
            raise ValueError("exact requires a string gold")
        return text == normalize(gold)
    items = _items(gold)
    if rule == "contains_all":
        return all(find_bounded(text, item) >= 0 for item in items)
    if rule == "ordered":
        pos = 0
        for item in items:
            found = find_bounded(text, item, pos)
            if found < 0:
                return False
            pos = found + len(item)
        return True
    raise ValueError(f"unknown scoring_rule {rule}")


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            die(f"{path}:{lineno}: {exc}")
        if not isinstance(row, dict):
            die(f"{path}:{lineno}: expected object")
        rows.append(row)
    if not rows:
        die(f"{path}: no rows")
    return rows


def _check_case(row: dict, index: int) -> None:
    missing = [key for key in REQUIRED if key not in row]
    if missing:
        die(f"case {index}: missing {missing}")
    if not isinstance(row["id"], str) or not row["id"]:
        die(f"case {index}: bad id")
    if not isinstance(row["category"], str) or not row["category"]:
        die(f"case {index}: bad category")
    if row["scoring_rule"] not in RULES:
        die(f"{row['id']}: bad scoring_rule")
    if not isinstance(row["tags"], list) or not row["tags"]:
        die(f"{row['id']}: tags must be a non-empty list")
    if not isinstance(row["generator_note"], str) or len(row["generator_note"]) < 20:
        die(f"{row['id']}: generator_note missing")
    if not isinstance(row["input"], str) or not row["input"].strip():
        die(f"{row['id']}: empty input")
    if not isinstance(row["question"], str) or not row["question"].strip():
        die(f"{row['id']}: empty question")


def score_files(cases_path: Path, preds_path: Path) -> int:
    cases = load_jsonl(cases_path)
    preds = load_jsonl(preds_path)
    seen = set()
    for index, row in enumerate(cases, 1):
        _check_case(row, index)
        if row["id"] in seen:
            die(f"duplicate case id {row['id']}")
        seen.add(row["id"])
    pred_map: dict[str, str] = {}
    for row in preds:
        if "id" not in row or "output" not in row:
            die("prediction rows need id and output")
        pid = row["id"]
        if pid in pred_map:
            die(f"duplicate prediction id {pid}")
        if not isinstance(row["output"], str):
            die(f"{pid}: output must be a string")
        pred_map[pid] = row["output"]

    by_cat = defaultdict(lambda: [0, 0])
    fails = []
    for row in cases:
        cid = row["id"]
        cat = row["category"]
        by_cat[cat][0] += 1
        output = pred_map.get(cid)
        if output is None:
            fails.append((cid, cat, row["scoring_rule"], "MISSING", row["gold"]))
            continue
        try:
            ok = passes(row["scoring_rule"], row["gold"], output)
        except ValueError as exc:
            die(f"{cid}: {exc}")
        if ok:
            by_cat[cat][1] += 1
        else:
            shown = output.replace("\n", " ")
            if len(shown) > 80:
                shown = shown[:77] + "..."
            fails.append((cid, cat, row["scoring_rule"], shown, row["gold"]))

    for pid in pred_map:
        if pid not in seen:
            print(f"WARN unknown prediction id {pid}", file=sys.stderr)

    print(f"{'category':<24} {'n':>4} {'correct':>8} {'accuracy':>8}")
    total_n = 0
    total_ok = 0
    for cat in sorted(by_cat):
        n, ok = by_cat[cat]
        total_n += n
        total_ok += ok
        acc = ok / n if n else 0.0
        print(f"{cat:<24} {n:4d} {ok:8d} {acc:8.3f}")
    overall = total_ok / total_n if total_n else 0.0
    print(f"{'OVERALL':<24} {total_n:4d} {total_ok:8d} {overall:8.3f}")
    for cid, cat, rule, got, gold in fails:
        print(f"FAIL\t{cid}\t{cat}\t{rule}\tgot={got}\tgold={gold}")
    return 1 if fails else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score Kiln long-context JSONL predictions.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--preds", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.cases.is_file():
        die(f"missing cases: {args.cases}")
    if not args.preds.is_file():
        die(f"missing preds: {args.preds}")
    return score_files(args.cases, args.preds)


if __name__ == "__main__":
    raise SystemExit(main())
