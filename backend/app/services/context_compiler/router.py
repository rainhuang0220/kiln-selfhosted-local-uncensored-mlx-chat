"""Put a short live-scene pin at the end of the default user-side context."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import re
from typing import Any


_RECALL = re.compile(r"回忆|过去|以前|第一次|初次|初见|那天|当时|记得|发生过|见面在哪里")
_IDENTITY = re.compile(r"你(?:是|扮演|是什么|的身份)|什么身份|你是谁")
_PERSON_LOOKUP = re.compile(r"是谁|什么关系|背景|认识|身份")
_ASK_BACKGROUND = re.compile(r"背景|现实")
_SCENE_CAP = 160
_PREFERENCE_CAP = 120
_EXPLICIT_PREFERENCE = re.compile(r"^[（(]\s*(怎么服务|服务|称呼|叫法|不要做|不要|偏好)\s*[:：]\s*(.+?)\s*[）)]$")


@dataclass(frozen=True)
class RouteResult:
    intent: str
    fence: str
    reference_fence: str | None = None


def _value(value: Any, cap: int = 180) -> str:
    return escape(str(value or "").strip()[:cap], quote=False)


def _scene_line(ir: dict[str, Any]) -> str:
    persona = ir.get("persona") if isinstance(ir.get("persona"), dict) else {}
    avatar = ir.get("user_avatar") if isinstance(ir.get("user_avatar"), dict) else {}
    scene = str(ir.get("current_scene") or "").strip()
    scene = re.split(r"以下(?:内容|是)|幻想参考|信息背景和性癖参考|仅作为参考", scene, maxsplit=1)[0].strip()
    role = str(persona.get("role") or "").strip()
    identity = str(avatar.get("identity") or "").strip()
    parts = [part for part in (role, identity) if part and part not in scene]
    if scene:
        parts.append(scene)
    return f"此刻现场：{_value('；'.join(parts), _SCENE_CAP)}"


def _short_explicit_preferences(ir: dict[str, Any], scene_line: str) -> str:
    """Only literal, short 括号 preferences; no inferred style or rule bank."""
    names = {str(item.get("name") or "") for item in ir.get("entities") or []}
    aliases = ir.get("aliases") if isinstance(ir.get("aliases"), dict) else {}
    names.update(str(name) for name in aliases)
    names.update(str(name) for name in aliases.values())
    offstage = {name for name in names if name and name not in scene_line}
    lines: list[str] = []
    for segment in ir.get("segments") or []:
        match = _EXPLICIT_PREFERENCE.match(str(segment.get("text") or "").strip())
        if not match:
            continue
        line = f"{match.group(1)}：{match.group(2).strip()}"
        if any(name in line for name in offstage) or line in lines:
            continue
        if len("\n".join([*lines, line])) > _PREFERENCE_CAP:
            continue
        lines.append(line)
    return "\n".join(_value(line, _PREFERENCE_CAP) for line in lines)


def route_context(ir: dict[str, Any], message: str, *, active_names: list[str] | None = None) -> RouteResult:
    """Default hop carries the live room; named recall adds only named events."""
    query = (message or "").strip()
    scene_line = _scene_line(ir)
    mentioned = [item for item in ir.get("entities") or [] if item.get("name") and item["name"] in query]
    identity = bool(_IDENTITY.search(query)) and not mentioned
    recall = not identity and (bool(_RECALL.search(query)) or bool(mentioned and _PERSON_LOOKUP.search(query)))
    ask_background = bool(_ASK_BACKGROUND.search(query)) and not recall

    if recall:
        names = {item["name"] for item in mentioned} or set(active_names or [])
        events = [
            item for item in ir.get("events") or []
            if not item.get("needs_review") and names.intersection(item.get("actors") or [])
        ][:4]
        if events or mentioned:
            refs = []
            for item in mentioned[:3]:
                line = f"参考人物：{_value(item['name'], 80)}；{_value(item.get('identity'), 120)}"
                if item.get("note"):
                    line += f"；{_value(item['note'], 120)}"
                refs.append(line)
            refs.extend(
                f"参考事件：{_value('、'.join(event.get('actors') or []), 100)}；{_value(event.get('description'), 180)}"
                for event in events
            )
            reference = "\n".join(refs)
            return RouteResult("recall", f"{scene_line}\n{reference}", reference)

    if ask_background:
        avatar = ir.get("user_avatar") if isinstance(ir.get("user_avatar"), dict) else {}
        background = avatar.get("real_background")
        if background and background != "暂无":
            return RouteResult("background", f"现实设定：{_value(background, 160)}\n{scene_line}")

    if identity:
        return RouteResult("identity", scene_line)

    preference = _short_explicit_preferences(ir, scene_line)
    fence = f"{preference}\n{scene_line}" if preference else scene_line
    return RouteResult("roleplay", fence)
