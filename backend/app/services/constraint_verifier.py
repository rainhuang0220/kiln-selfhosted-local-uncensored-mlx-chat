"""Fidelity verifier: extract atomic constraints, then check a compiled prompt.

This is not a content filter. It only asks whether requested facts survived.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Typed bilingual lexicon. Conflicts are typed opposites of an extracted
# constraint, not a growing raw antonym list applied to whole strings.
_SPECS: list[dict[str, Any]] = [
    {
        "type": "count",
        "value": "3",
        "extract": (r"恰好有三个人", r"三个人", r"三个", r"exactly three", r"\bthree\b"),
        "aliases": ("exactly three", "three people", "3 people", "三人", "三个", "three"),
        "conflicts": ("exactly four", "four people", "四个", "四人", "four"),
    },
    {
        "type": "count",
        "value": "4",
        "extract": (r"恰好有四个人", r"四个人", r"四个", r"exactly four", r"\bfour\b"),
        "aliases": ("exactly four", "four people", "4 people", "四人", "四个", "four"),
        "conflicts": ("exactly three", "three people", "三个", "三人", "three"),
    },
    {
        "type": "color",
        "value": "red",
        "extract": (r"红色", r"\bred\b"),
        "aliases": ("red", "红色"),
        "conflicts": ("blue", "蓝色"),
    },
    {
        "type": "color",
        "value": "blue",
        "extract": (r"蓝色", r"\bblue\b"),
        "aliases": ("blue", "蓝色"),
        "conflicts": ("red", "红色"),
    },
    {
        "type": "relation",
        "value": "left_of",
        "extract": (r"左侧", r"左边", r"\bleft of\b", r"\bleft\b"),
        "aliases": ("left of", "to the left", "left", "左侧", "左边"),
        "conflicts": ("right of", "to the right", "右侧", "右边"),
    },
    {
        "type": "relation",
        "value": "right_of",
        "extract": (r"右侧", r"右边", r"\bright of\b"),
        "aliases": ("right of", "to the right", "right", "右侧", "右边"),
        "conflicts": ("left of", "to the left", "左侧", "左边"),
    },
    {
        "type": "pose",
        "value": "standing",
        "extract": (r"站着", r"站立", r"不要坐下", r"\bstanding\b"),
        "aliases": ("standing", "stand", "站着", "站立"),
        "conflicts": ("sitting", "sit", "坐下", "坐着"),
    },
    {
        "type": "pose",
        "value": "sitting",
        "extract": (r"坐着", r"(?<!不要)坐下", r"\bsitting\b"),
        "aliases": ("sitting", "sit", "坐着", "坐下"),
        "conflicts": ("standing", "stand", "站着", "站立"),
    },
    {
        "type": "time",
        "value": "night",
        "extract": (r"夜晚", r"夜里", r"\bnight\b"),
        "aliases": ("night", "nighttime", "夜晚", "夜里"),
        "conflicts": ("daytime", "daytime", "白天", "day "),
    },
    {
        "type": "time",
        "value": "day",
        "extract": (r"白天", r"\bdaytime\b"),
        "aliases": ("daytime", "daylight", "白天"),
        "conflicts": ("night", "夜晚"),
    },
    {
        "type": "place",
        "value": "indoor",
        "extract": (r"室内", r"\bindoor\b"),
        "aliases": ("indoor", "interior", "室内"),
        "conflicts": ("outdoor", "outdoors", "室外"),
    },
    {
        "type": "place",
        "value": "outdoor",
        "extract": (r"室外", r"\boutdoor\b"),
        "aliases": ("outdoor", "outdoors", "室外"),
        "conflicts": ("indoor", "interior", "室内"),
    },
    {
        "type": "view",
        "value": "front",
        "extract": (r"正面", r"\bfront view\b"),
        "aliases": ("front", "frontal", "正面"),
        "conflicts": ("back", "rear", "背面"),
    },
    {
        "type": "view",
        "value": "back",
        "extract": (r"背面", r"\bback view\b"),
        "aliases": ("back", "rear", "背面"),
        "conflicts": ("front", "frontal", "正面"),
    },
    {
        "type": "camera",
        "value": "overhead",
        "extract": (r"俯视", r"正上方", r"\boverhead\b", r"top-down"),
        "aliases": ("overhead", "top-down", "top down", "from above", "俯视", "正上方"),
        "conflicts": ("low-angle", "low angle", "仰视"),
    },
    {
        "type": "camera",
        "value": "low_angle",
        "extract": (r"仰视", r"\blow[- ]angle\b"),
        "aliases": ("low-angle", "low angle", "仰视"),
        "conflicts": ("overhead", "top-down", "俯视"),
    },
]


def _norm(text: str) -> str:
    return (text or "").lower()


def _has(haystack: str, needle: str) -> bool:
    if not needle:
        return False
    if re.search(r"[\u4e00-\u9fff]", needle):
        return needle in haystack
    if needle.endswith(" ") or needle.startswith(" "):
        return needle.lower() in haystack
    return re.search(rf"\b{re.escape(needle.lower())}\b", haystack, flags=re.I) is not None


def extract_constraints(text: str) -> list[dict[str, Any]]:
    raw = text or ""
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for spec in _SPECS:
        if not any(re.search(pat, raw, flags=re.I) for pat in spec["extract"]):
            continue
        key = (spec["type"], str(spec["value"]))
        if key in seen:
            continue
        seen.add(key)
        found.append(
            {
                "type": spec["type"],
                "value": spec["value"],
                "aliases": list(spec["aliases"]),
                "conflicts": list(spec["conflicts"]),
            }
        )
    return found


def constraints_against_text(constraints: list[dict[str, Any]], effective: str) -> list[dict[str, Any]]:
    hay = _norm(effective)
    report = []
    for item in constraints:
        aliases = item.get("aliases") or [str(item.get("value", ""))]
        conflicts = item.get("conflicts") or []
        kept = any(_has(hay, a) or _has(effective, a) for a in aliases)
        swapped = (not kept) and any(_has(hay, c) or _has(effective, c) for c in conflicts)
        status = "pass" if kept else "fail"
        report.append(
            {
                "type": item.get("type"),
                "value": item.get("value"),
                "status": status,
                "reason": "ok" if kept else ("swapped" if swapped else "dropped"),
            }
        )
    return report


def structured_violations(original: str, effective: str) -> list[str]:
    report = constraints_against_text(extract_constraints(original), effective)
    return [f"{row['type']}:{row['value']}:{row['reason']}" for row in report if row["status"] != "pass"]


EXTRACT_SYSTEM = """You extract atomic visual constraints from a user prompt.
This is a fidelity check, not a safety filter.
Return only JSON: {"constraints":[{"type":"count|color|relation|pose|time|place|camera|subject|action","value":"...","subject":"..."}]}
Do not add constraints the user did not state.
"""


def parse_constraint_json(text: str) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return []
    data = json.loads(raw[start : end + 1])
    items = data.get("constraints") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if isinstance(item, dict) and item.get("type") and item.get("value") is not None:
            out.append({"type": str(item["type"]), "value": item["value"], **{k: item[k] for k in item if k not in {"type", "value"}}})
    return out


def extract_constraints_model(text: str, complete_fn) -> list[dict[str, Any]]:
    drafted = complete_fn(EXTRACT_SYSTEM, text)
    parsed = parse_constraint_json(drafted)
    return parsed or extract_constraints(text)
