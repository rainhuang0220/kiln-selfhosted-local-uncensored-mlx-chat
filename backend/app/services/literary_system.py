"""Short immersive system text; the live scene is supplied on the user side."""

from __future__ import annotations

from typing import Any, Mapping

IMMERSIVE_SYSTEM = """写成人向文爱小说。用户已打开 NSFW，按他这一句的方向大胆写。
先接上一句用户输入，再写这一拍。不要用辞藻填字，不要复读上一拍。
当前房间以这条消息末尾的「此刻现场」为准。参考日记里的人和事，没点名就不是现场。"""

GROUNDED_CONTEXT_SYSTEM = IMMERSIVE_SYSTEM


def compile_system(card: Mapping[str, Any] | None = None, *, grounded_context: bool = False) -> str:
    """Use the short system block for bound context; keep explicit standalone cards."""
    base = (GROUNDED_CONTEXT_SYSTEM if grounded_context else IMMERSIVE_SYSTEM).strip()
    if not card or grounded_context:
        return base
    immutable = card.get("immutable_json") or card.get("immutable") or []
    if isinstance(immutable, str):
        immutable_text = immutable.strip()
    else:
        immutable_text = "；".join(str(x).strip() for x in immutable if str(x).strip())
    parts = [
        base,
        "",
        "<character>",
        f"name: {(card.get('name') or '').strip()}",
        f"personality: {(card.get('personality') or '').strip()}",
        f"speech: {(card.get('speech_style') or card.get('speech') or '').strip()}",
        f"taboos: {(card.get('taboos') or '').strip()}",
        f"relationship: {(card.get('relationship_to_user') or card.get('relationship') or '').strip()}",
        f"immutable: {immutable_text}",
        f"scenario: {(card.get('scenario') or '').strip()}",
        f"description: {(card.get('description') or '').strip()}",
        "</character>",
    ]
    if card.get("first_mes"):
        parts.insert(-1, f"first_mes: {str(card.get('first_mes')).strip()}")
    if card.get("mes_example"):
        parts.insert(-1, f"mes_example: {str(card.get('mes_example')).strip()}")
    return "\n".join(parts)
