"""Visible-body counters for long-form narrative acceptance.

Counts only user-visible prose. Whitespace is stripped for acceptance; Han
characters are reported separately. Prompt text, thinking, and metadata must
never be mixed into these counters.
"""

from __future__ import annotations

import math
import re

_WS = re.compile(r"\s+", re.UNICODE)


def count_visible_chars(text: str) -> int:
    if not text:
        return 0
    return len(_WS.sub("", text))


def count_han(text: str) -> int:
    if not text:
        return 0
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def estimate_tokens_for_chars(chars: int, *, chars_per_token: float = 1.6) -> int:
    if chars <= 0:
        return 0
    return max(1, int(round(chars / max(chars_per_token, 0.1))))


def segment_char_budget(
    target_visible_chars: int,
    *,
    segment_chars: int = 2500,
) -> list[int]:
    """Split a work-level character target into per-segment budgets."""
    target = max(1, int(target_visible_chars))
    size = max(1, int(segment_chars))
    n = max(1, math.ceil(target / size))
    budgets = [size] * n
    budgets[-1] = target - size * (n - 1)
    return budgets
