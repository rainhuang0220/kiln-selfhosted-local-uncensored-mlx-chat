"""Continuity checks for narrative segments."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.narrative_chars import count_visible_chars

_USER_AGENCY_PATTERNS = [
    re.compile(r"你决定了"),
    re.compile(r"你选择了"),
    re.compile(r"你心中暗想"),
    re.compile(r"你忍不住说"),
    re.compile(r"you decide(?:d)? to", re.I),
]


@dataclass
class ContinuityReport:
    ok: bool
    reasons: list[str]
    repeat_ratio: float
    agency_hits: list[str]


def _ngram_repeat_ratio(text: str, n: int = 24) -> float:
    visible = re.sub(r"\s+", "", text)
    if len(visible) < n * 2:
        return 0.0
    grams = [visible[i : i + n] for i in range(0, len(visible) - n + 1, n // 2)]
    if not grams:
        return 0.0
    uniq = len(set(grams))
    return 1.0 - (uniq / len(grams))


def check_segment(
    text: str,
    *,
    prior_text: str = "",
    forbid_user_agency: bool = True,
    min_chars: int = 200,
    max_repeat_ratio: float = 0.45,
) -> ContinuityReport:
    reasons: list[str] = []
    agency: list[str] = []
    visible = count_visible_chars(text)
    if visible < min_chars:
        reasons.append(f"too_short:{visible}")
    ratio = _ngram_repeat_ratio(text)
    if ratio >= max_repeat_ratio:
        reasons.append(f"internal_repeat:{ratio:.2f}")
    if prior_text:
        # Detect large exact prefix/suffix overlaps with prior accepted prose.
        tail = re.sub(r"\s+", "", prior_text)[-400:]
        head = re.sub(r"\s+", "", text)[:400]
        if tail and head and (tail in head or head in tail):
            reasons.append("overlap_prior")
    if forbid_user_agency:
        for pat in _USER_AGENCY_PATTERNS:
            m = pat.search(text)
            if m:
                agency.append(m.group(0))
        if agency:
            reasons.append("user_agency_violation")
    return ContinuityReport(
        ok=not reasons,
        reasons=reasons,
        repeat_ratio=ratio,
        agency_hits=agency,
    )
