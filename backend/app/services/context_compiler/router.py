"""Select only task-relevant Context IR for a generation turn.

Attention layers (V16):
  L0 ALWAYS-ON — ROLE / USER_AVATAR / CURRENT_SCENE (live parlor), ≤400 chars total.
  L1 ASKED-ONLY — USER_BACKGROUND when the user asks 背景/现实; entity one-liners on name mention.
  L2 RETRIEVED — at most one 80-char preference hint on default hop; bound events on named recall.
  L3 NEVER — raw source, DOCUMENT_META, UNKNOWN, off-stage people as current_cast.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import re
from typing import Any


_RECALL = re.compile(r"回忆|过去|以前|第一次|初次|初见|那天|当时|记得|发生过|见面在哪里")
_IDENTITY = re.compile(r"你(?:是|扮演|是什么|的身份)|什么身份|你是谁")
_PERSON_LOOKUP = re.compile(r"是谁|什么关系|背景|认识|身份")
_ASK_BACKGROUND = re.compile(r"背景|现实")
_BARE_OPEN = re.compile(r"^(?:你好|您好|开始(?:聊天)?|嗨|哈喽|在吗)[\s。！？!?～~]*$")
_CUE_PREF = re.compile(r"以下内容|仅作为参考|信息背景和性癖参考|幻想参考|性癖参考")
_L0_CAP = 400
_SCENE_CAP = 160
_PREF_CAP = 80


@dataclass(frozen=True)
class RouteResult:
    intent: str
    fence: str
    reference_fence: str | None = None


def _value(value: Any, cap: int = 180) -> str:
    return escape(str(value or "").strip()[:cap], quote=False)


def _style_prefs(ir: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in ir.get("preferences") or []:
        if not item.get("do_not_literalize"):
            continue
        content = str(item.get("content") or "").strip()
        if not content or _CUE_PREF.search(content):
            continue
        out.append(item)
    return out


def _l0_block(ir: dict[str, Any], *, active_names: list[str] | None) -> list[str]:
    """Always-on live parlor lock — short ROLE / avatar / scene only."""
    persona = ir.get("persona") if isinstance(ir.get("persona"), dict) else {}
    avatar = ir.get("user_avatar") if isinstance(ir.get("user_avatar"), dict) else {}
    role = _value(persona.get("role"), 80)
    identity = _value(avatar.get("identity"), 120)
    scene = _value(ir.get("current_scene"), _SCENE_CAP)
    # Never let a cue sentence masquerade as the live scene.
    scene = re.split(r"以下(?:内容|是)|幻想参考|信息背景和性癖参考|仅作为参考", scene, maxsplit=1)[0].strip()
    lines = [
        "<active_context>",
        "仅当前场景和角色身份定义此刻；参考资料不是已发生的当前场景。",
    ]
    if role:
        lines.append(f"assistant_persona: {role}")
    if scene:
        lines.append(f"重点现实场景: {scene}")
        lines.append(f"current_scene: {scene}")
    if identity:
        lines.append(f"user_avatar: {identity}")
    # On-stage cast only when the live scene line names them.
    for name in (active_names or [])[:8]:
        if name and name in (ir.get("current_scene") or ""):
            entity = next((item for item in ir.get("entities") or [] if item.get("name") == name), None)
            if entity:
                lines.append(f"current_cast: {_value(name, 80)}；{_value(entity.get('identity'), 120)}")
    lines.append("</active_context>")
    # Hard cap L0: drop optional cast lines first, then trim scene if still over.
    text = "\n".join(lines)
    if len(text) <= _L0_CAP:
        return lines
    lines = [ln for ln in lines if not ln.startswith("current_cast:")]
    text = "\n".join(lines)
    if len(text) <= _L0_CAP:
        return lines
    # Last resort: shrink scene fields.
    trimmed: list[str] = []
    for ln in lines:
        if ln.startswith("重点现实场景:") or ln.startswith("current_scene:"):
            head, _, _ = ln.partition(": ")
            trimmed.append(f"{head}: {_value(ir.get('current_scene'), 80)}")
        else:
            trimmed.append(ln)
    return trimmed


def route_context(ir: dict[str, Any], message: str, *, active_names: list[str] | None = None) -> RouteResult:
    """Default roleplay excludes history. Recall uses named, verified events only."""
    query = (message or "").strip()
    lines = _l0_block(ir, active_names=active_names)
    mentioned = [item for item in ir.get("entities") or [] if item.get("name") and item["name"] in query]
    identity = bool(_IDENTITY.search(query)) and not mentioned
    recall = not identity and (bool(_RECALL.search(query)) or bool(mentioned and _PERSON_LOOKUP.search(query)))
    ask_background = bool(_ASK_BACKGROUND.search(query)) and not recall
    bare = bool(_BARE_OPEN.match(query)) or not query

    if identity:
        return RouteResult("identity", "\n".join(lines))

    if recall:
        names = {item["name"] for item in mentioned} or set(active_names or [])
        events = [
            item for item in ir.get("events") or []
            if not item.get("needs_review") and names.intersection(item.get("actors") or [])
        ][:4]
        if events or mentioned:
            refs = [
                "<reference_context>",
                "参考（不可当成当前店内事实）",
                "以下为历史或幻想记录，只用于回答本次回忆问题；不要让人物自动进入当前场景。",
            ]
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

    # L1 ASKED-ONLY: background / compact entity lines — never on bare 你好.
    if ask_background and not bare:
        avatar = ir.get("user_avatar") if isinstance(ir.get("user_avatar"), dict) else {}
        bg = avatar.get("real_background")
        if bg and bg != "暂无":
            lines.append(f"现实设定: {_value(bg, 160)}")
        for entity in mentioned[:3]:
            lines.append(
                f"现实设定: {_value(entity.get('name'), 80)}；{_value(entity.get('identity'), 120)}"
            )

    # L2: at most one short preference hint on default hop — never six blobs.
    prefs = _style_prefs(ir)
    if prefs:
        hint = _value(prefs[0].get("content"), _PREF_CAP)
        if hint:
            lines.append(
                "<preference_bank do_not_literalize=\"true\">"
                "偏好只影响表达与服务方式，不能当作角色身份或已发生事件复述。"
            )
            lines.append(hint)
            lines.append("</preference_bank>")

    fence = "\n".join(lines)
    # Soft total guard for default hop (L0 + optional one hint).
    if len(fence) > 500 and "<preference_bank" in fence:
        fence = fence.split("<preference_bank", 1)[0].rstrip()
    return RouteResult("roleplay", fence)
