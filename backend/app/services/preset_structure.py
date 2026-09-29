"""Fast, source-grounded event structure for a long character preset.

The sequence is the order in the user's text. A temporal cue is retained as
written; unrelated memories are never assigned a fabricated shared date.
"""

from __future__ import annotations

import re
from typing import Any


_SENTENCE = re.compile(r"[^。！？!?\n]+[。！？!?]?")
_ACTION = re.compile(
    r"说|问|看|叫|把|递|送|敲|推|走|去|来|回|站|坐|借|留|寄|发|"
    r"剪|穿|拉|按|放|等|改|提醒|带|拿|握|倾|数|冲|记|忘|开|关|见面|遇见|认识"
)
_WHEN = re.compile(
    r"(?:小学[一二三四五六1-6]年级|初[一二三123]|高[一二三123]|昨天|前天|去年|前年|"
    r"毕业以后|分开以后|离职那天|打烊后|闭馆以后|停电的那个夏天|"
    r"有一年夏天|有年冬天|那天|那晚|那年|后来|有次|有一次|"
    r"周末|夏天|冬天|雨季里|雨天|下班以后|每天|当时)"
)
_IDENTITY = re.compile(r"^[\u4e00-\u9fff]{2,3}是[^。！？!?]{0,32}(?:室友|同事|邻居|表哥|店员|店主|管理员|助教|同桌|教练|上司|前任|朋友|同学|认识的人)")


def _person_segments(paragraph: str, known: list[str]) -> list[str]:
    """Recover person blocks when a paste has no paragraph breaks."""
    present = [name for name in known if name in paragraph]
    if len(paragraph) < 450 or len(present) < 3:
        return [paragraph]
    groups: list[str] = []
    current: list[str] = []
    current_name = ""
    for match in _SENTENCE.finditer(paragraph):
        sentence = match.group(0)
        stripped = sentence.lstrip()
        direct = [name for name in present if name in sentence]
        leading = next((name for name in direct if stripped.startswith(name)), "")
        next_name = leading or (min(direct, key=lambda name: sentence.find(name)) if direct else "")
        if next_name and current_name and next_name != current_name and current:
            groups.append("".join(current))
            current = []
        if next_name:
            current_name = next_name
        current.append(sentence)
    if current:
        groups.append("".join(current))
    return groups


def extract_timeline(source: str, corpus: str, names: list[str], *, cap: int = 36) -> list[dict[str, Any]]:
    """Collect up to three events per reference paragraph with exact spans."""
    known = [name for name in names if name]
    if not source or not corpus or not known:
        return []
    timeline: list[dict[str, Any]] = []
    source_cursor = 0
    paragraphs = [
        segment
        for paragraph in re.split(r"\n\s*\n", corpus)
        for segment in _person_segments(paragraph, known)
    ]
    for paragraph in paragraphs:
        if not paragraph.strip():
            continue
        counts = {name: paragraph.count(name) for name in known}
        paragraph_name = max(counts, key=counts.get) if counts and max(counts.values()) else ""
        candidates: list[dict[str, Any]] = []
        for match in _SENTENCE.finditer(paragraph):
            raw = match.group(0).strip()
            if len(raw) < 8 or not _ACTION.search(raw) or _IDENTITY.match(raw):
                continue
            if (
                "不是人名" in raw or "补充说明" in raw or "解析时" in raw
                or "不能盖过" in raw or "真正的" in raw or raw.startswith(("这句话", "我是"))
                or raw.startswith(("现实背景", "真实背景", "明确偏好", "偏好", "幻想参考", "信息背景"))
            ):
                continue
            mentioned = [name for name in known if name in raw]
            if not mentioned and not paragraph_name:
                continue
            at = source.find(raw, source_cursor)
            if at < 0:
                at = source.find(raw)
            if at < 0:
                continue
            source_cursor = at + len(raw)
            cue = _WHEN.search(raw)
            candidates.append({
                "id": f"ev-{at}",
                "order": 0,
                "who": mentioned,
                "suggested_who": [paragraph_name] if not mentioned and paragraph_name else [],
                "summary": raw.rstrip("。！？!?")[:100],
                "when": cue.group(0) if cue else "未注明",
                "chronology": "source_order",
                "scope": "reference",
                "evidence": raw,
                "source_span": {"start": at, "end": at + len(raw)},
                "needs_review": not bool(mentioned),
            })
        if not candidates:
            continue
        picks: list[int] = [0]
        temporal = [i for i, event in enumerate(candidates) if event["when"] != "未注明" and i != 0]
        if temporal:
            picks.append(temporal[-1])
            if len(picks) < 3 and temporal[0] not in picks:
                picks.append(temporal[0])
        if len(picks) < 3 and len(candidates) - 1 not in picks:
            picks.append(len(candidates) - 1)
        if len(picks) < 3:
            middle = len(candidates) // 2
            if middle not in picks:
                picks.append(middle)
        for i in sorted(set(picks))[:3]:
            timeline.append(candidates[i])
        if len(timeline) >= cap:
            break
    timeline.sort(key=lambda item: item["source_span"]["start"])
    for order, item in enumerate(timeline, start=1):
        item["order"] = order
    return timeline


def normalize_timeline(raw: Any) -> list[dict[str, Any]]:
    """Retain editable event fields while bounding storage and prompt size."""
    if not isinstance(raw, list):
        return []
    events = []
    seen = set()
    for at, item in enumerate(raw[:40], start=1):
        if not isinstance(item, dict):
            continue
        identity = str(item.get("id") or f"manual-{at}").strip()[:64]
        if identity in seen:
            continue
        seen.add(identity)
        span = item.get("source_span") if isinstance(item.get("source_span"), dict) else {}
        start = span.get("start")
        end = span.get("end")
        participants = item.get("who")
        if isinstance(participants, str):
            participants = re.split(r"[、,，;；/]+", participants)
        suggestions = item.get("suggested_who")
        if isinstance(suggestions, str):
            suggestions = re.split(r"[、,，;；/]+", suggestions)
        events.append({
            "id": identity,
            "order": at,
            "who": list(dict.fromkeys(str(name).strip()[:120] for name in (participants or [])[:8] if str(name).strip())),
            "suggested_who": [str(name).strip()[:120] for name in (suggestions or [])[:3] if str(name).strip()],
            "summary": str(item.get("summary") or "").strip()[:100],
            "when": str(item.get("when") or "未注明").strip()[:40],
            "chronology": "source_order",
            "scope": "active" if item.get("scope") == "active" else "reference",
            "evidence": str(item.get("evidence") or "").strip()[:160],
            "source_span": {"start": start, "end": end} if isinstance(start, int) and isinstance(end, int) and 0 <= start < end else None,
            "needs_review": bool(item.get("needs_review")),
        })
    return events
