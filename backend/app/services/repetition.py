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


# A closing parenthesis ends a 括号 action line; those recur verbatim in paragraph cycles.
_TERMINATORS = "。！？!?…）)"
_CLOSERS = "”」』\"'"


def repeated_sentence_start(text: str, *, min_chars: int = 16, prior: str = "") -> int | None:
    """Start of the just-finished sentence if it already appears earlier in text.

    Catches multi-paragraph cycles that never repeat back-to-back. Short
    refrains (a quoted line under min_chars) are allowed to recur. ``prior`` is
    the previous reply: a turn that re-types its sentences is looping too.
    """
    end = len(text.rstrip())
    k = end
    while k > 0 and text[k - 1] in _CLOSERS:
        k -= 1
    if k == 0 or text[k - 1] not in _TERMINATORS:
        return None
    j = k - 1
    while j > 0 and text[j - 1] in _TERMINATORS:
        j -= 1
    while j > 0 and text[j - 1] not in _TERMINATORS and text[j - 1] != "\n":
        j -= 1
    start = j
    while start < end and (text[start].isspace() or text[start] in "”」』"):
        start += 1
    sentence = text[start:end]
    if len(_WS.sub("", sentence)) < min_chars:
        return None
    if text.find(sentence, 0, start) != -1 or (prior and sentence in prior):
        return start
    return None


_PUNCT = re.compile(r"[\s，,。！？!?…（）()“”「」『』、；;：:—\-*]+")


def _sentence_spans(text: str) -> list[tuple[int, str]]:
    spans, begin = [], 0
    for i, ch in enumerate(text):
        if ch not in _TERMINATORS and ch != "\n":
            continue
        if i + 1 < len(text) and text[i + 1] in _TERMINATORS:
            continue
        piece = text[begin : i + 1]
        core = _PUNCT.sub("", piece)
        if core:
            spans.append((begin + len(piece) - len(piece.lstrip()), core))
        begin = i + 1
    return spans


def refrain_run_start(
    text: str, *, window: int = 6, hits: int = 3, gram: int = 4, min_chars: int = 8
) -> int | None:
    """Cut index when one short phrase recurs in ``hits`` of the last ``window`` sentences.

    Catches slot-filled templates (「手臂也放松一下」「背部也放松一下」…) and option
    menus whose lines differ in one word, so no whole sentence ever repeats. The
    first sentence of the run is kept; the cut lands on the second.
    """
    body = text.rstrip()
    if not body or body[-1] not in _TERMINATORS:
        return None
    spans = [s for s in _sentence_spans(body) if len(s[1]) >= min_chars]
    if len(spans) < window:
        return None
    tail = spans[-window:]
    grams = [{core[i : i + gram] for i in range(len(core) - gram + 1)} for _, core in tail]
    for piece in grams[-1]:
        idx = [k for k, found in enumerate(grams) if piece in found]
        if len(idx) >= hits:
            return tail[idx[1]][0]
    return None


def _trigrams(text: str) -> set[str]:
    compact = _WS.sub("", text)
    return {compact[i : i + 3] for i in range(len(compact) - 2)}


def tail_window_loop(text: str, *, window: int = 400, threshold: float = 0.45) -> int | None:
    """Cut index when the last ``window`` chars mostly re-say the ``window`` before them.

    Catches cycles built from short questions and 括号 lines that never repeat one
    ≥16-char sentence back-to-back. Ordinary prose stays under ~0.2 trigram Jaccard.
    """
    if len(text) < 2 * window:
        return None
    before, after = _trigrams(text[-2 * window : -window]), _trigrams(text[-window:])
    if not before or not after:
        return None
    if len(before & after) / len(before | after) < threshold:
        return None
    cut = len(text) - window
    for i in range(cut - 1, -1, -1):
        if text[i] in _TERMINATORS or text[i] == "\n":
            cut = i + 1
            break
    # The window before is already loop material; peel sentences said earlier.
    head = text[:cut].rstrip()
    while (start := repeated_sentence_start(head, min_chars=2)) is not None:
        head = head[:start].rstrip()
    return len(head)


def hard_self_loop(text: str, *, min_repeats: int = 3, min_chars: int = 40) -> str | None:
    """Return the looping sentence if it appears consecutively >= min_repeats times.

    Short 文爱 sensory clauses (breath / contact deepening under ``min_chars``)
    are allowed to recur; three consecutive full sentences still trip the guard.
    """
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
