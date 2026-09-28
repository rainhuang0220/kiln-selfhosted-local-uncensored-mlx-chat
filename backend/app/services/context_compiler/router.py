"""Select only task-relevant Context IR for a generation turn."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import re
from typing import Any


_RECALL = re.compile(r"回忆|过去|以前|第一次|初次|初见|那天|当时|记得|发生过|见面在哪里")
_IDENTITY = re.compile(r"你(?:是|扮演|是什么|的身份)|什么身份|你是谁")
_PERSON_LOOKUP = re.compile(r"是谁|什么关系|背景|认识|身份")


@dataclass(frozen=True)
class RouteResult:
    intent: str
    fence: str
    reference_fence: str | None = None


def _value(value: Any, cap: int = 180) -> str:
    return escape(str(value or "").strip()[:cap], quote=False)


def route_context(ir: dict[str, Any], message: str, *, active_names: list[str] | None = None) -> RouteResult:
    """Default roleplay excludes history. Recall uses named, verified events only."""
    query = message or ""
    persona = ir.get("persona") if isinstance(ir.get("persona"), dict) else {}
    avatar = ir.get("user_avatar") if isinstance(ir.get("user_avatar"), dict) else {}
    role = _value(persona.get("role"), 80)
    lines = ["<active_context>", "仅当前场景和角色身份定义此刻；参考资料不是已发生的当前场景。"]
    if role:
        lines.append(f"assistant_persona: {role}")
    if ir.get("current_scene"):
        lines.append(f"current_scene: {_value(ir['current_scene'], 320)}")
    if avatar.get("identity"):
        lines.append(f"user_avatar: {_value(avatar['identity'], 120)}")
    if avatar.get("real_background") and avatar["real_background"] != "暂无":
        lines.append(f"confirmed_background: {_value(avatar['real_background'], 240)}")
    for name in (active_names or [])[:8]:
        entity = next((item for item in ir.get("entities") or [] if item.get("name") == name), None)
        if entity:
            lines.append(f"current_cast: {_value(name, 80)}；{_value(entity.get('identity'), 120)}")
    lines.append("</active_context>")
    mentioned = [item for item in ir.get("entities") or [] if item.get("name") and item["name"] in query]
    identity = bool(_IDENTITY.search(query)) and not mentioned
    recall = not identity and (bool(_RECALL.search(query)) or bool(mentioned and _PERSON_LOOKUP.search(query)))
    if identity:
        return RouteResult("identity", "\n".join(lines))
    if recall:
        names = {item["name"] for item in mentioned} or set(active_names or [])
        events = [
            item for item in ir.get("events") or []
            if not item.get("needs_review") and names.intersection(item.get("actors") or [])
        ][:4]
        if events or mentioned:
            refs = ["<reference_context>", "以下为历史或幻想记录，只用于回答本次回忆问题；不要让人物自动进入当前场景。"]
            for entity in mentioned[:3]:
                line = f"参考人物：{_value(entity['name'], 80)}；身份：{_value(entity.get('identity'), 120)}"
                if entity.get("note"):
                    line += f"；备注：{_value(entity['note'], 120)}"
                refs.append(line)
            for event in events:
                refs.append(
                    f"参考事件：文本顺序{event.get('order')}，时间线索{_value(event.get('time'), 40)}；"
                    f"涉及{_value('、'.join(event.get('actors') or []), 100)}；{_value(event.get('description'), 180)}"
                )
            refs.append("</reference_context>")
            reference = "\n".join(refs)
            return RouteResult("recall", "\n".join(lines) + "\n\n" + reference, reference)
    prefs = [item for item in ir.get("preferences") or [] if item.get("do_not_literalize")]
    if prefs:
        lines.append("<preference_bank do_not_literalize=\"true\">偏好只影响表达与服务方式，不能当作角色身份或已发生事件复述。")
        for item in prefs[:6]:
            lines.append(_value(item.get("content"), 160))
        lines.append("</preference_bank>")
    return RouteResult("roleplay", "\n".join(lines))
