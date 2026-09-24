#!/usr/bin/env python3
"""Offline flags for a compressed prompt. Stdlib only; no model and no network.

Flags dropped numbers (including YYYY-MM-DD dates), dropped negation cues
(不 / 没 / not / never), reordered numbered lines, and missing code identifiers
(snake_case, simple CamelCase, or backtick names). It does not judge facts.
"""

from __future__ import annotations

import re
import sys
from collections import Counter

# Dates before thousand-groups before decimals before bare integers.
_NUMBER = re.compile(
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{4}/\d{2}/\d{2}"
    r"|\d{1,3}(?:,\d{3})+(?:\.\d+)?"
    r"|\d+\.\d+"
    r"|\d+"
)
_NEGATION = re.compile(r"不|没|\bnot\b|\bnever\b", re.IGNORECASE)
_NUMBERED_LINE = re.compile(r"(?m)^[ \t]*(\d+)[ \t]*[.、)][ \t]*(.+?)\s*$")
_IDENT = re.compile(
    r"`([A-Za-z_][A-Za-z0-9_]*)`"
    r"|\b([A-Za-z_][A-Za-z0-9]*_[A-Za-z0-9_]+)\b"
    r"|\b([A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+)\b"
    r"|\b([a-z]+(?:[A-Z][a-z0-9]+)+)\b"
)


def _deficit(original: list[str], compressed: list[str]) -> list[str]:
    left = Counter(compressed)
    missing: list[str] = []
    for item in original:
        if left[item] > 0:
            left[item] -= 1
        else:
            missing.append(item)
    return missing


def find_dropped_numbers(original: str, compressed: str) -> list[str]:
    return _deficit(_NUMBER.findall(original), _NUMBER.findall(compressed))


def find_dropped_negations(original: str, compressed: str) -> list[str]:
    def cues(text: str) -> list[str]:
        found = []
        for match in _NEGATION.finditer(text):
            cue = match.group(0)
            found.append(cue.lower() if cue.isascii() else cue)
        return found

    return _deficit(cues(original), cues(compressed))


def _numbered_lines(text: str) -> list[tuple[str, str]]:
    rows = []
    for number, body in _NUMBERED_LINE.findall(text):
        rows.append((number, re.sub(r"\s+", " ", body).strip()))
    return rows


def _kept_order_broke(original: list[str], compressed: list[str]) -> bool:
    """True when items that still appear are not in their original order.

    Deletions keep relative order and are not a reorder. Repeated items use
    the first original index.
    """
    first: dict[str, int] = {}
    for index, item in enumerate(original):
        first.setdefault(item, index)
    seen = [first[item] for item in compressed if item in first]
    return any(seen[i] >= seen[i + 1] for i in range(len(seen) - 1))


def find_reordered_numbered_lines(original: str, compressed: str) -> list[str]:
    orig = _numbered_lines(original)
    comp = _numbered_lines(compressed)
    flags: list[str] = []
    orig_nums = [number for number, _ in orig]
    comp_nums = [number for number, _ in comp]
    if _kept_order_broke(orig_nums, comp_nums):
        flags.append("numbers " + " ".join(orig_nums) + " => " + " ".join(comp_nums))
    orig_bodies = [body for _, body in orig]
    comp_bodies = [body for _, body in comp]
    if _kept_order_broke(orig_bodies, comp_bodies):
        flags.append(
            "bodies " + " | ".join(orig_bodies) + " => " + " | ".join(comp_bodies)
        )
    return flags


def find_missing_code_identifiers(original: str, compressed: str) -> list[str]:
    def idents(text: str) -> list[str]:
        found = []
        for match in _IDENT.finditer(text):
            found.append(next(group for group in match.groups() if group))
        return found

    return _deficit(idents(original), idents(compressed))


def audit(original: str, compressed: str) -> dict[str, list[str]]:
    return {
        "dropped_numbers": find_dropped_numbers(original, compressed),
        "dropped_negations": find_dropped_negations(original, compressed),
        "reordered_numbered_lines": find_reordered_numbered_lines(original, compressed),
        "missing_code_identifiers": find_missing_code_identifiers(original, compressed),
    }


_CLEAN_ORIG = (
    "请注意：不要删除 user_id。金额是 42 元，日期 2026-09-24。\n"
    "1. 先备份\n"
    "2. 再迁移\n"
)
_CLEAN_COMP = (
    "不要删除 user_id。金额是 42 元，日期 2026-09-24。\n"
    "1. 先备份\n"
    "2. 再迁移\n"
)
_NUM_ORIG = "不要删除 user_id。金额是 42 元，日期 2026-09-24。\n1. 保留\n2. 核对\n"
_NUM_COMP = "不要删除 user_id。金额是元，日期。\n1. 保留\n2. 核对\n"
_NEG_ORIG = "do not ship and never retry。不要回滚，没确认。\n1. 编译\n2. 测试\n3. 发布\n"
_NEG_COMP = "ship and retry。要回滚，确认。\n1. 编译\n3. 发布\n2. 测试\n"
_CODE_ORIG = "调用 parse_user_id(user_id) 与 `ChatService`。\n1. 打开\n2. 保存\n"
_CODE_COMP = "调用 (user_id) 与服务。\n1. 打开\n2. 保存\n"

CASES = [
    (
        "clean_keeps_constraints",
        _CLEAN_ORIG,
        _CLEAN_COMP,
        {
            "dropped_numbers": [],
            "dropped_negations": [],
            "reordered_numbered_lines": [],
            "missing_code_identifiers": [],
        },
    ),
    (
        "drops_number_and_date",
        _NUM_ORIG,
        _NUM_COMP,
        {
            "dropped_numbers": ["42", "2026-09-24"],
            "dropped_negations": [],
            "reordered_numbered_lines": [],
            "missing_code_identifiers": [],
        },
    ),
    (
        "drops_negation_and_reorders",
        _NEG_ORIG,
        _NEG_COMP,
        {
            "dropped_numbers": [],
            "dropped_negations": ["not", "never", "不", "没"],
            "reordered_numbered_lines": [
                "numbers 1 2 3 => 1 3 2",
                "bodies 编译 | 测试 | 发布 => 编译 | 发布 | 测试",
            ],
            "missing_code_identifiers": [],
        },
    ),
    (
        "drops_code_identifier",
        _CODE_ORIG,
        _CODE_COMP,
        {
            "dropped_numbers": [],
            "dropped_negations": [],
            "reordered_numbered_lines": [],
            "missing_code_identifiers": ["parse_user_id", "ChatService"],
        },
    ),
]


def main() -> int:
    failed = False
    for name, original, compressed, expected in CASES:
        got = audit(original, compressed)
        if got == expected:
            print(f"PASS {name}")
        else:
            failed = True
            print(f"FAIL {name}")
            print(f"  expected={expected}")
            print(f"  got={got}")
    print("FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
