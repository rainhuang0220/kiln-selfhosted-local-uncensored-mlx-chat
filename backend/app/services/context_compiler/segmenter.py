"""Locate typed clauses without turning document text into instructions."""

from __future__ import annotations

import re
from typing import Any

from app.services.style_bank import split_style_corpus


_SENTENCE = re.compile(r"[^。！？!?\n]+[。！？!?]?")
_ROLE = re.compile(r"^你(?:是|扮演)")
_AVATAR = re.compile(r"^我(?:是|叫|扮演)")
_BACKGROUND = re.compile(r"^(?:现实背景|真实背景|个人背景|我的背景)[:：]")
_PREFERENCE = re.compile(r"^(?:明确偏好|用户偏好|我的偏好|性癖偏好|风格偏好|偏好)[:：]")
_IMPLICIT_PREFERENCE = re.compile(r"^我(?:喜欢|偏爱|更喜欢|希望|倾向于)")
_INLINE_PREF = re.compile(r"括号里的内容|性癖参考|禁止照搬|供后续服务学习|喜欢被照顾")
_REFERENCE_META = re.compile(r"^(?:以下|以上|补充说明|这些|这句话|真正的|解析时)")
_ACTION = re.compile(r"说|问|把|递|送|敲|推|走|去|来|站|坐|借|寄|发|剪|穿|拉|放|等|带|拿|握|开|关|见面|遇见")
_TITLE_ONLY = re.compile(r"^[\w\u4e00-\u9fff]{2,12}$")

TYPES = frozenset({
    "ROLE_DEFINITION", "USER_AVATAR", "USER_BACKGROUND", "USER_PREFERENCE",
    "CURRENT_SCENE", "ENTITY_DEFINITION", "ENTITY_ATTRIBUTE", "WORLD_EVENT",
    "DOCUMENT_META", "UNKNOWN",
})


def _clauses(source: str):
    for sentence in _SENTENCE.finditer(source):
        raw = sentence.group(0)
        # A live opening commonly defines both roles in one sentence.
        cuts = [0]
        if raw.lstrip().startswith("你"):
            match = re.search(r"[，,]\s*(?=我(?:是|叫|扮演))", raw)
            if match:
                cuts = [0, match.end()]
            # Peel inline preference cue off the role clause.
            pref = re.search(r"[，,]\s*(?=括号里的内容)", raw)
            if pref:
                cuts = sorted(set(cuts + [pref.start(), pref.end()]))
            cuts = sorted(set(cuts + [len(raw)]))
        if len(cuts) == 1:
            cuts = [0, len(raw)]
        for left, right in zip(cuts, cuts[1:]):
            piece = raw[left:right]
            stripped = piece.strip(" \t\r\n，,")
            if not stripped:
                continue
            local = piece.find(stripped)
            start = sentence.start() + left + local
            yield start, start + len(stripped), stripped


def segment_document(source: str, names: list[str], event_evidence: set[str]) -> list[dict[str, Any]]:
    """Produce source-aligned segments; no text is promoted across its scope."""
    split = split_style_corpus(source)
    reference_start = source.find(split.corpus) if split.corpus else len(source)
    if reference_start < 0:
        reference_start = len(source)
    segments = []
    seen_meta: set[str] = set()
    seen_avatar = False
    for start, end, text in _clauses(source):
        if text in {"）", ")"}:
            continue
        scope = "live" if start < reference_start else "reference"
        name = next((candidate for candidate in names if candidate in text), "")
        plain = text.lstrip("（( ")
        if _TITLE_ONLY.match(text) and "你" not in text and "我" not in text and len(text) <= 12:
            kind = "DOCUMENT_META"
        elif _ROLE.match(text) and scope == "live":
            kind = "ROLE_DEFINITION"
        elif _AVATAR.match(text) and (scope == "live" or not seen_avatar):
            kind = "USER_AVATAR"
            seen_avatar = True
        elif _BACKGROUND.match(text):
            kind = "USER_BACKGROUND"
        elif _PREFERENCE.match(text) or _IMPLICIT_PREFERENCE.match(text) or _INLINE_PREF.search(plain):
            kind = "USER_PREFERENCE"
        elif _REFERENCE_META.match(plain) or "不是人名" in text or "不能盖过" in text:
            kind = "DOCUMENT_META"
        elif not name and re.search(r"喜欢|偏爱|语气|节奏|感觉", text):
            kind = "UNKNOWN"
        elif any(evidence in text or text in evidence for evidence in event_evidence):
            kind = "WORLD_EVENT"
        elif name and (
            re.search(rf"{re.escape(name)}是", text)
            or re.search(rf"是{re.escape(name)}", text)
            or re.search(rf"{re.escape(name)}[，,]\s*\d{{1,2}}岁", text)
        ):
            kind = "ENTITY_DEFINITION"
        elif name and _ACTION.search(text):
            kind = "WORLD_EVENT"
        elif name:
            kind = "ENTITY_ATTRIBUTE"
        elif scope == "live":
            kind = "CURRENT_SCENE"
        else:
            kind = "UNKNOWN"
        if kind == "DOCUMENT_META":
            if text in seen_meta:
                continue
            seen_meta.add(text)
        if kind == "USER_AVATAR":
            seen_avatar = True
        segments.append({
            "id": f"seg-{start}",
            "text": text,
            "type": kind,
            "scope": scope,
            "importance": 1.0 if kind in {"ROLE_DEFINITION", "USER_AVATAR", "CURRENT_SCENE"} else 0.8 if kind == "USER_PREFERENCE" else 0.6 if kind == "ENTITY_DEFINITION" else 0.4,
            "source_span": {"start": start, "end": end},
            "needs_review": kind == "UNKNOWN",
        })
    return segments[:600]
