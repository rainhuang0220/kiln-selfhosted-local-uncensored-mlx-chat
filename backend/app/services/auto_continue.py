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
    completion_tokens_used: int = 0,
    completion_soft_cap: int = 0,
) -> bool:
    """Continue the same assistant message_id toward min_output_chars.

    Triggers on stop / length / completed_length while under the visible-char
    floor. Does not inject a synthetic user "continue" turn.

    When ``completion_soft_cap`` > 0, hops stop once cumulative completion
    tokens across the turn reach that soft budget (immersive default 12288).
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
    if completion_soft_cap > 0 and completion_tokens_used >= completion_soft_cap:
        return False
    finish = (finish_reason or "").strip().lower()
    return finish in {"length", "completed_length", "stop", "completed_stop", ""}


def counts_against_continue_budget(unique_chars: int, *, min_unique: int = 80) -> bool:
    """Guard-aborted hops that add almost nothing must not burn a useful continue slot."""
    return int(unique_chars or 0) >= min_unique


def hard_provider_call_cap(auto_continue_max: int) -> int:
    """Total MLX calls this turn: existing useful cap if ≥6, else 6 (room for refunds)."""
    cap = int(auto_continue_max or 0)
    return cap if cap >= 6 else 6


_CLAUSE_BREAK = set("。！？!?；;，,、：:…—\n\r\t 「」『』“”‘’\"'（）()《》·~～")
_SENTENCE_END = set("。！？!?…」』”\n")


def runon_start(text: str, *, limit: int = 80) -> int | None:
    """Index where an unpunctuated tail of >= limit chars begins, else None.

    Chinese prose almost never runs 80 chars without a comma; when it does,
    the model has fallen into a word list.
    """
    run = 0
    for i in range(len(text) - 1, -1, -1):
        if text[i] in _CLAUSE_BREAK:
            break
        run += 1
    if run >= limit:
        return len(text) - run
    return None


def trim_to_sentence(text: str, *, min_chars: int) -> str:
    """Drop a dangling half-sentence if the floor still holds without it."""
    for i in range(len(text) - 1, -1, -1):
        if text[i] in _SENTENCE_END:
            head = text[: i + 1]
            if head != text and count_output_chars(head) >= min_chars:
                return head
            return text
    return text


def drop_last_sentence(text: str) -> str:
    """Text up to the end of the second-to-last sentence, or text if there is none."""
    end = len(text.rstrip())
    while end > 0 and text[end - 1] in _SENTENCE_END:
        end -= 1
    for i in range(end - 1, -1, -1):
        if text[i] in _SENTENCE_END:
            return text[: i + 1]
    return text


def fill_hop_tokens(
    *,
    visible_chars: int,
    visible_tokens: int,
    min_output_chars: int,
    cap: int,
    margin_chars: int = 1200,
) -> int:
    """max_tokens for an EOS-suppressed hop that lands past the floor."""
    if visible_chars <= 0 or visible_tokens <= 0:
        return max(1, cap)
    chars_per_token = visible_chars / visible_tokens
    need = max(0, min_output_chars + margin_chars - visible_chars)
    tokens = int(need / chars_per_token) + 64
    return max(1, min(cap, max(256, tokens)))
