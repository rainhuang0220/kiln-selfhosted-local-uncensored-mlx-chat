"""Decide when to auto-continue a chat turn toward a visible-char target."""

from __future__ import annotations

import re

_LOW_INFO = re.compile(
    r"^(嗯+|然后呢|继续|是吗|好+|……|\.{2,}|展开|写长一点|往下写|再说)$"
)
_CONTINUE_HINT = re.compile(r"(继续|展开|写长一点|往下写|再说|续写)")


def count_output_chars(text: str) -> int:
    """汉字+字母等非空白字符；与 prompt 合同一致。"""
    if not text:
        return 0
    return sum(1 for ch in text if not ch.isspace())


def is_low_info(user_text: str) -> bool:
    t = (user_text or "").strip()
    if not t:
        return True
    if len(t) <= 4 and _LOW_INFO.match(t):
        return True
    return bool(_LOW_INFO.match(t))


def wants_long_output(user_text: str) -> bool:
    return bool(_CONTINUE_HINT.search(user_text or ""))


def should_auto_continue(
    *,
    visible_chars: int,
    finish_reason: str | None,
    min_output_chars: int,
    auto_continue_count: int,
    auto_continue_max: int,
    user_text: str = "",
    repetition_guard: bool = False,
) -> bool:
    """Continue the same assistant message_id toward min_output_chars.

    Triggers on stop / length / completed_length while under the visible-char
    floor. Does not inject a synthetic user "continue" turn.
    """
    del user_text  # reserved for future gating; length floor is authoritative
    if repetition_guard:
        return False
    if auto_continue_max <= 0 or auto_continue_count >= auto_continue_max:
        return False
    if min_output_chars <= 0:
        return False
    if visible_chars >= min_output_chars:
        return False
    finish = (finish_reason or "").strip().lower()
    return finish in {"length", "completed_length", "stop", "completed_stop", ""}
