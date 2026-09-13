"""Offline repetition metrics plus a conservative runtime self-loop guard."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SENT_SPLIT = re.compile(r"(?<=[。！？!?\n])")
_WS = re.compile(r"\s+")


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT.split(text or "") if p and p.strip()]
    if parts:
        return parts
    collapsed = _WS.sub(" ", (text or "").strip())
    return [collapsed] if collapsed else []


def _norm(sentence: str) -> str:
    return _WS.sub("", sentence).lower()


def _char_ngrams(text: str, n: int) -> list[str]:
    compact = _WS.sub("", text)
    if len(compact) < n:
        return []
    return [compact[i : i + n] for i in range(len(compact) - n + 1)]


def _longest_repeat(text: str) -> str:
    compact = _WS.sub("", text)
    best = ""
    n = len(compact)
    if n < 8:
        return ""
    # Bound the search so runtime guard stays cheap on long streams.
    window = compact[-4000:]
    limit = min(len(window) // 2, 240)
    for size in range(limit, 7, -1):
        needle = window[-size:]
        if window[:-size].find(needle) >= 0:
            return needle
    return best


@dataclass
class RepetitionReport:
    sentence_count: int
    duplicate_sentence_ratio: float
    repeated_3gram_ratio: float
    repeated_4gram_ratio: float
    longest_repeated_substring: str
    same_paragraph_recurrence: int
    near_duplicate_sentence_count: int
    immediate_self_loop_count: int

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "sentence_count": self.sentence_count,
            "duplicate_sentence_ratio": self.duplicate_sentence_ratio,
            "repeated_3gram_ratio": self.repeated_3gram_ratio,
            "repeated_4gram_ratio": self.repeated_4gram_ratio,
            "longest_repeated_substring": self.longest_repeated_substring,
            "same_paragraph_recurrence": self.same_paragraph_recurrence,
            "near_duplicate_sentence_count": self.near_duplicate_sentence_count,
            "immediate_self_loop_count": self.immediate_self_loop_count,
        }


def _ngram_repeat_ratio(text: str, n: int) -> float:
    grams = _char_ngrams(text, n)
    if not grams:
        return 0.0
    seen: dict[str, int] = {}
    for g in grams:
        seen[g] = seen.get(g, 0) + 1
    repeated = sum(c for c in seen.values() if c > 1)
    return repeated / len(grams)


def _near_dupes(sentences: list[str]) -> int:
    norms = [_norm(s) for s in sentences]
    count = 0
    for i, a in enumerate(norms):
        if len(a) < 4:
            continue
        for b in norms[i + 1 :]:
            if a == b:
                count += 1
                break
            if len(b) >= 4 and (a in b or b in a) and abs(len(a) - len(b)) <= max(4, len(a) // 5):
                count += 1
                break
    return count


def score_repetition(text: str) -> RepetitionReport:
    sentences = _sentences(text)
    norms = [_norm(s) for s in sentences if _norm(s)]
    dup_ratio = 0.0
    if norms:
        unique = set(norms)
        dup_ratio = (len(norms) - len(unique)) / len(norms)
    loops = 0
    run = 1
    for i in range(1, len(norms)):
        if norms[i] == norms[i - 1] and len(norms[i]) >= 8:
            run += 1
            if run >= 2:
                loops += 1
        else:
            run = 1
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text or "") if p.strip()]
    para_recurrence = 0
    seen_para: dict[str, int] = {}
    for p in paragraphs:
        key = _norm(p)
        if not key:
            continue
        seen_para[key] = seen_para.get(key, 0) + 1
    para_recurrence = sum(c - 1 for c in seen_para.values() if c > 1)
    return RepetitionReport(
        sentence_count=len(sentences),
        duplicate_sentence_ratio=dup_ratio,
        repeated_3gram_ratio=_ngram_repeat_ratio(text, 3),
        repeated_4gram_ratio=_ngram_repeat_ratio(text, 4),
        longest_repeated_substring=_longest_repeat(text),
        same_paragraph_recurrence=para_recurrence,
        near_duplicate_sentence_count=_near_dupes(sentences),
        immediate_self_loop_count=loops,
    )


def hard_self_loop(text: str, *, min_repeats: int = 3, min_chars: int = 8) -> str | None:
    """Return the looping sentence if it appears consecutively >= min_repeats times."""
    norms_and_raw = [(_norm(s), s.strip()) for s in _sentences(text)]
    if len(norms_and_raw) < min_repeats:
        # Also catch an unterminated tail that reprints the same clause.
        compact = _WS.sub("", text or "")
        if len(compact) >= min_chars * min_repeats:
            size = min(len(compact) // min_repeats, 80)
            for n in range(size, min_chars - 1, -1):
                piece = compact[-n:]
                if compact.endswith(piece * min_repeats):
                    return piece
        return None
    run = 1
    for i in range(1, len(norms_and_raw)):
        prev, cur = norms_and_raw[i - 1][0], norms_and_raw[i][0]
        if cur and cur == prev and len(cur) >= min_chars:
            run += 1
            if run >= min_repeats:
                return norms_and_raw[i][1]
        else:
            run = 1
    return None
