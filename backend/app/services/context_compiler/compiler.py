"""Compile a long preset draft into typed, source-grounded Context IR."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .segmenter import TYPES, segment_document


_ROLE = re.compile(r"你(?:是|扮演)(?:一名|一个|一位|位)?([^，,。；;\n]{1,50})")
_RELATION = (
    ("姐姐", "sister_of"), ("妹妹", "sister_of"),
    ("哥哥", "brother_of"), ("弟弟", "brother_of"),
    ("表哥", "cousin_of"), ("表妹", "cousin_of"),
    ("室友", "roommate_of"), ("同事", "colleague_of"),
    ("朋友", "friend_of"), ("同桌", "classmate_of"),
)


def _clean(value: Any, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def _apply_verified_edits(source: str, segments: list[dict[str, Any]], previous: Any) -> None:
    if not isinstance(previous, list):
        return
    edits = {str(item.get("id")): item for item in previous if isinstance(item, dict)}
    for segment in segments:
        edited = edits.get(segment["id"])
        if not edited or edited.get("text") != segment["text"] or edited.get("source_span") != segment["source_span"]:
            continue
        kind = edited.get("type")
        if kind not in TYPES:
            continue
        # A reference paragraph cannot become a high-priority live role or scene.
        if segment["scope"] == "reference" and kind in {"ROLE_DEFINITION", "USER_AVATAR", "CURRENT_SCENE"}:
            continue
        segment["type"] = kind
        segment["needs_review"] = kind == "UNKNOWN"


def compile_context(source: str, draft: dict[str, Any]) -> dict[str, Any]:
    """Single compiler seam: source + editable draft -> versioned Context IR."""
    prior = draft.get("context_ir") if isinstance(draft.get("context_ir"), dict) else {}
    characters = draft.get("characters") or []
    timeline = draft.get("timeline") or []
    names = [_clean(item.get("name"), 120) for item in characters if isinstance(item, dict)]
    evidence = {_clean(item.get("evidence"), 300) for item in timeline if isinstance(item, dict) and item.get("evidence")}
    segments = segment_document(source, names, evidence)
    _apply_verified_edits(source, segments, prior.get("segments"))

    role_segment = next((item for item in segments if item["type"] == "ROLE_DEFINITION"), None)
    role_match = _ROLE.search(role_segment["text"]) if role_segment else None
    role = _clean(role_match.group(1), 50) if role_match else ""
    me = draft.get("me") if isinstance(draft.get("me"), dict) else {}
    avatar = _clean(me.get("identity"), 120)
    if avatar == "暂无":
        avatar = ""
    pref_segments = [item for item in segments if item["type"] == "USER_PREFERENCE"]
    preferences = []
    for item in pref_segments:
        content = re.sub(r"^[^:：]{1,12}[:：]", "", item["text"]).strip()
        if content:
            preferences.append({
                "id": f"pref-{item['source_span']['start']}",
                "category": "style_or_preference",
                "content": _clean(content, 240),
                "do_not_literalize": True,
                "source_span": item["source_span"],
            })
    explicit = _clean(me.get("explicit_prefs"), 600)
    manual_prior = any(item.get("id") == "pref-manual" for item in prior.get("preferences") or [])
    explicit_changed = bool(prior) and explicit != _clean(prior.get("preference_field_at_compile"), 600)
    if explicit and explicit != "暂无" and (manual_prior or explicit_changed or (not prior and not pref_segments)):
        # A manual edit in the visible preference field supersedes source-derived style.
        preferences = [{
            "id": "pref-manual", "category": "style_or_preference", "content": explicit,
            "do_not_literalize": True, "source_span": None,
        }]
    entities = []
    relations = []
    known_names = {name for name in names if name}
    for item in characters[:32]:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        name = _clean(item["name"], 120)
        identity = _clean(item.get("identity"), 120)
        entities.append({
            "id": _clean(item.get("id"), 64) or f"person-{name}",
            "name": name, "identity": identity,
            "note": _clean(item.get("one_event"), 120), "scope": "reference",
        })
        for cue, relation in _RELATION:
            if cue in identity:
                target = next((other for other in known_names if other != name and identity.startswith(other + "的")), None)
                if target is None and re.search(rf"{re.escape(name)}是我[^。！？!?]{{0,30}}{re.escape(cue)}", source):
                    target = "user"
                if target:
                    relations.append({"subject": name, "predicate": relation, "object": target, "evidence": identity})
                break
    valid_event_spans = [s["source_span"] for s in segments if s["type"] == "WORLD_EVENT"]
    events = []
    for item in timeline[:40]:
        if not isinstance(item, dict) or item.get("scope") == "active":
            continue
        span = item.get("source_span")
        if not isinstance(span, dict) or not any(start["start"] <= span.get("start", -1) and span.get("end", -1) <= start["end"] for start in valid_event_spans):
            continue
        events.append({
            "id": _clean(item.get("id"), 64),
            "order": item.get("order"),
            "actors": list(item.get("who") or []),
            "description": source[span["start"]:span["end"]],
            "note": _clean(item.get("summary"), 160),
            "time": _clean(item.get("when"), 40),
            "source_span": span,
            "certainty": "fictional" if "幻想" in source[:100] else "reported",
            "needs_review": bool(item.get("needs_review")),
        })
    conflicts = [
        {
            "kind": "avatar_claim_in_reference",
            "evidence": item["text"],
            "source_span": item["source_span"],
            "resolution": "kept_live_avatar",
        }
        for item in segments
        if item["scope"] == "reference"
        and item["type"] != "USER_AVATAR"
        and re.match(r"^我(?:是|叫|扮演)", item["text"])
    ]
    scene = _clean(draft.get("current_scene"), 160)
    # The reference-introduction sentence is metadata, never a live scene.
    scene = re.split(r"以下(?:内容|是)|幻想参考|信息背景和性癖参考|仅作为参考", scene, maxsplit=1)[0].strip()
    if scene in {"测试长文本", "长文本"} or (len(scene) <= 12 and "你" not in scene and "店" not in scene):
        role_line = next((item["text"] for item in segments if item["type"] == "ROLE_DEFINITION"), "")
        scene = _clean(role_line, 160) or scene
    # Prefer a labeled parlor line already extracted by the live splitter.
    labeled = re.search(r"当前场景\s*[:：]\s*(.+)", scene)
    if labeled:
        scene = _clean(labeled.group(1), 160)
    scene = _clean(scene, 160)
    # Prefer the first USER_AVATAR segment when the studio me.identity slot is empty.
    if not avatar:
        av = next((item for item in segments if item["type"] == "USER_AVATAR"), None)
        if av:
            avatar = _clean(av["text"], 120)
    return {
        "version": 2,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "segments": segments,
        "persona": {"role": role, "rules": []},
        "user_avatar": {"identity": avatar, "real_background": _clean(me.get("real_background"), 600)},
        "current_scene": scene,
        "entities": entities,
        "relations": relations,
        "events": events,
        "preferences": preferences,
        "conflicts": conflicts,
        "preference_field_at_compile": explicit,
    }
