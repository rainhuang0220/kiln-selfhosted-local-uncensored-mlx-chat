"""Bind timeline candidates to known people; drop orphans instead of asking the user."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from app.services.preset_structure import normalize_timeline


_UNDER18 = re.compile(
    r"(?:未满十八|未成年|儿童|\d{1,2}岁|小学[一二三四五六1-6]年级|初[一二三123]|高[一二三123])"
)
_SEXUAL = re.compile(
    r"(?:上床|做爱|性交|性爱|发生关系|性暗示|抚摸私处|亲吻身体)"
)
_DROP = "DROP"
_GOLD_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "preset_ten_people.gold_ir.json"


def _clean(value: Any, limit: int = 160) -> str:
    return str(value or "").strip()[:limit]


def _known_names(draft: dict[str, Any]) -> list[str]:
    return [
        _clean(item.get("name"), 120)
        for item in (draft.get("characters") or [])
        if isinstance(item, dict) and _clean(item.get("name"), 120)
    ]


def _avatar_is_under18(source: str, draft: dict[str, Any]) -> bool:
    me = draft.get("me") if isinstance(draft.get("me"), dict) else {}
    head = " ".join([
        _clean(me.get("identity"), 120),
        source[:240],
    ])
    return bool(_UNDER18.search(head))


def _is_sexual_event(text: str) -> bool:
    return bool(_SEXUAL.search(text or ""))


def _parse_who_decision(decision: str, known: list[str]) -> list[str] | None:
    """Accept a single name, comma/space list, JSON list, or DROP."""
    token = (decision or "").strip()
    if not token or token == _DROP:
        return None
    known_set = set(known)
    if token in known_set:
        return [token]
    if token.startswith("["):
        try:
            raw = json.loads(token)
        except json.JSONDecodeError:
            raw = None
        if isinstance(raw, list):
            names = [str(item).strip() for item in raw if str(item).strip() in known_set]
            return names[:4] or None
    parts = [p.strip() for p in re.split(r"[,，、/\s]+", token) if p.strip()]
    names = [p for p in parts if p in known_set]
    if names:
        return names[:4]
    return None


def _pick_who(event: dict[str, Any], known: list[str], decision: str | None) -> list[str] | None:
    """Closed set: every known name in evidence (max 4) or None to DROP."""
    if decision:
        return _parse_who_decision(decision, known)
    who = [name for name in (event.get("who") or []) if name in known]
    evidence = _clean(event.get("evidence") or event.get("summary"), 400)
    mentioned = [name for name in known if name and name in evidence]
    # Stable order = first appearance in the evidence clip.
    mentioned.sort(key=lambda name: evidence.find(name))
    if mentioned:
        # Keep the full co-actor set from evidence (shared beats), not mentioned[0] only.
        return mentioned[:4]
    if who:
        who_sorted = sorted(who, key=lambda name: evidence.find(name) if name in evidence else 10**9)
        return who_sorted[:4]
    for name in event.get("suggested_who") or []:
        if name in known:
            return [name]
    return None


def _who_set(event: dict[str, Any]) -> frozenset[str]:
    return frozenset(event.get("who") or [])


def _merge_consecutive(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge only when the who-set is equal; different co-actor sets stay separate rows."""
    if not events:
        return []
    merged: list[dict[str, Any]] = []
    for event in events:
        if merged and _who_set(merged[-1]) == _who_set(event) and _who_set(event):
            prev = merged[-1]
            note = _clean(event.get("summary"), 80)
            if note and note not in (prev.get("summary") or ""):
                prev["summary"] = _clean(f"{prev.get('summary')}；{note}", 100)
            if event.get("when") and event["when"] != "未注明":
                if prev.get("when") in {"", "未注明", None}:
                    prev["when"] = event["when"]
                elif event["when"] not in str(prev.get("when") or ""):
                    prev["when"] = f"{prev['when']}·{event['when']}"[:40]
            continue
        merged.append(dict(event))
    for order, item in enumerate(merged, start=1):
        item["order"] = order
        item["needs_review"] = False
        item["suggested_who"] = []
    return merged

def _rewrite_character_notes(draft: dict[str, Any], events: list[dict[str, Any]]) -> None:
    """Fill empty one_event from the first bound beat for that person."""
    first: dict[str, str] = {}
    for event in events:
        for name in event.get("who") or []:
            if name not in first and event.get("summary"):
                first[name] = _clean(event["summary"], 40)
    for character in draft.get("characters") or []:
        if not isinstance(character, dict):
            continue
        name = character.get("name")
        if name in first and not character.get("one_event"):
            character["one_event"] = first[name]


def load_gold_shots(limit: int = 5) -> list[dict[str, str]]:
    """Few-shot clips from the adult ten-person gold IR (never chat-send)."""
    if not _GOLD_PATH.is_file():
        return []
    try:
        payload = json.loads(_GOLD_PATH.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    shots = []
    for event in (payload.get("events") or [])[:limit]:
        who = (event.get("who") or [""])[0]
        evidence = _clean(event.get("evidence"), 120)
        if who and evidence:
            shots.append({"who": who, "evidence": evidence})
    return shots


def bind_timeline_events(
    source: str,
    draft: dict[str, Any],
    *,
    decisions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Attach who[] from the closed name set, merge same-who beats, drop the rest.

    ``decisions`` maps event id → known name or ``DROP`` (for tests / teacher labels).
    Never leaves needs_review=true on retained events.
    """
    body = dict(draft)
    known = _known_names(body)
    under18 = _avatar_is_under18(source, body)
    decisions = decisions or {}
    bound: list[dict[str, Any]] = []
    for raw in normalize_timeline(body.get("timeline")):
        evidence = _clean(raw.get("evidence") or raw.get("summary"), 400)
        if under18 and _is_sexual_event(evidence):
            continue
        who = _pick_who(raw, known, decisions.get(str(raw.get("id") or "")))
        if not who:
            continue
        # Reject misalignment: drop names absent from evidence when others are present.
        if evidence:
            in_evidence = [name for name in who if name in evidence]
            if in_evidence:
                who = in_evidence
            elif len(who) == 1:
                others = [name for name in known if name in evidence and name != who[0]]
                if others:
                    others.sort(key=lambda name: evidence.find(name))
                    who = others[:4]
        item = dict(raw)
        item["who"] = who
        item["suggested_who"] = []
        item["needs_review"] = False
        item["summary"] = _clean(item.get("summary") or evidence, 100)
        bound.append(item)
    body["timeline"] = _merge_consecutive(bound)
    _rewrite_character_notes(body, body["timeline"])
    return body


def parse_binder_decisions(model_text: str, known: list[str], event_ids: list[str]) -> dict[str, str]:
    """Parse a closed-set binder JSON answer into id → name|DROP."""
    try:
        start, end = model_text.index("{"), model_text.rindex("}") + 1
        payload = json.loads(model_text[start:end])
    except (ValueError, json.JSONDecodeError):
        return {}
    rows = payload.get("decisions") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    known_set = set(known)
    out: dict[str, str] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        eid = str(raw.get("id") or "")
        if eid not in event_ids:
            continue
        who_raw = raw.get("who")
        if isinstance(who_raw, list):
            names = [str(item).strip() for item in who_raw if str(item).strip() in known_set]
            if names:
                out[eid] = "、".join(names[:4])
            else:
                out[eid] = _DROP
            continue
        answer = _clean(who_raw, 80)
        if answer == _DROP:
            out[eid] = _DROP
            continue
        parsed = _parse_who_decision(answer, known)
        if parsed:
            out[eid] = "、".join(parsed)
        elif answer in known_set:
            out[eid] = answer
    return out


def build_binder_prompt(
    source: str,
    draft: dict[str, Any],
    *,
    clips: list[dict[str, Any]],
) -> tuple[str, str]:
    """Return (system, user) for one batch of closed-set who decisions."""
    known = _known_names(draft)
    live = _clean((draft.get("current_scene") or "")[:120], 120)
    shots = load_gold_shots(4)
    system = (
        "你是同场人物判定器。只根据摘录选择和「我」同场的人。"
        "选项可以是已知人名的任意子集（逗号分隔或 JSON 列表），或 DROP。"
        "只输出 JSON：{\"decisions\":[{\"id\":\"\",\"who\":\"人名或人名列表或DROP\"}]}。"
        "不要解释，不要编造新人名。不要把不同场次的人合并。"
    )
    lines = [
        f"<live>{live}</live>",
        "已知人名：" + "、".join(known),
        "问题：这段里和「我」同场的人是谁？",
    ]
    if shots:
        lines.append("示例：")
        for shot in shots:
            lines.append(f"- 摘录「{shot['evidence']}」→ {shot['who']}")
    lines.append("待判定：")
    for item in clips:
        clip = _clean(item.get("evidence") or item.get("summary"), 400)
        lines.append(f"{item.get('id')} :: {clip}")
    lines.append("选项：已知人名的任意子集，或 " + _DROP)
    return system, "\n".join(lines)


async def bind_with_model(
    source: str,
    draft: dict[str, Any],
    provider: Any,
    *,
    complete: Callable[..., Any] | None = None,
    timeout_s: float = 25.0,
) -> dict[str, Any]:
    """Optional 9B fill for empty-who clips. Timeout keeps rules who or drops."""
    import asyncio

    from app.providers.base import ChatRequest

    body = bind_timeline_events(source, draft)
    # Re-read candidates that still need a model vote from the pre-bind timeline.
    known = _known_names(draft)
    pending = [
        item for item in normalize_timeline(draft.get("timeline"))
        if not [name for name in (item.get("who") or []) if name in known]
    ][:24]
    if not pending or provider is None:
        return body
    system, user = build_binder_prompt(source, draft, clips=pending)
    request = ChatRequest(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        top_p=0.8,
        top_k=20,
        max_tokens=512,
        enable_thinking=False,
    )
    try:
        runner = complete or provider.complete
        result = await asyncio.wait_for(runner(request), timeout=timeout_s)
        text = getattr(result, "content", None) or str(result)
        decisions = parse_binder_decisions(
            text, known, [str(item.get("id") or "") for item in pending],
        )
        return bind_timeline_events(source, draft, decisions=decisions)
    except Exception:
        return body
