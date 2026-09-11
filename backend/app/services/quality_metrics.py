"""Offline dialogue quality metrics. Not a runtime guard."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from statistics import median
from typing import Any, Iterable

_SENT_SPLIT = re.compile(r"(?<=[。！？!?…\n])")
_LOW_INFO = {
    "嗯",
    "嗯嗯",
    "然后呢",
    "然后",
    "好",
    "好的",
    "继续",
    "是吗",
    "……",
    "...",
    "…",
    "哦",
    "喔",
}


def normalize_cjk(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text or "")
    folded = folded.casefold()
    return re.sub(r"\s+", "", folded)


def sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT.split(text or "") if p and p.strip()]
    return parts or ([text.strip()] if text and text.strip() else [])


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    idx = min(len(ordered) - 1, max(0, round((p / 100) * (len(ordered) - 1))))
    return float(ordered[idx])


def exact_duplicate_sentence_ratio(texts: Iterable[str]) -> float:
    found: list[str] = []
    for text in texts:
        found.extend(sentences(text))
    if not found:
        return 0.0
    counts: dict[str, int] = {}
    for sent in found:
        counts[sent] = counts.get(sent, 0) + 1
    dupes = sum(n - 1 for n in counts.values() if n > 1)
    return dupes / len(found)


def normalized_duplicate_sentence_ratio(texts: Iterable[str]) -> float:
    found = [normalize_cjk(sent) for text in texts for sent in sentences(text)]
    found = [s for s in found if s]
    if not found:
        return 0.0
    counts: dict[str, int] = {}
    for sent in found:
        counts[sent] = counts.get(sent, 0) + 1
    dupes = sum(n - 1 for n in counts.values() if n > 1)
    return dupes / len(found)


def char_ngrams(text: str, n: int) -> list[str]:
    blob = normalize_cjk(text)
    if len(blob) < n:
        return []
    return [blob[i : i + n] for i in range(len(blob) - n + 1)]


def repeated_ngram_ratio(text: str, n: int) -> float:
    grams = char_ngrams(text, n)
    if not grams:
        return 0.0
    counts: dict[str, int] = {}
    for gram in grams:
        counts[gram] = counts.get(gram, 0) + 1
    repeated = sum(n_count - 1 for n_count in counts.values() if n_count > 1)
    return repeated / len(grams)


def char_ngram_repeat_ratio(text: str, n: int) -> float:
    return repeated_ngram_ratio(text, n)


def longest_repeated_substring(text: str, min_len: int = 4) -> str:
    blob = normalize_cjk(text)
    best = ""
    seen: dict[str, int] = {}
    for length in range(min_len, min(len(blob) // 2 + 1, 64) + 1):
        found = ""
        for i in range(0, len(blob) - length + 1):
            chunk = blob[i : i + length]
            prev = seen.get(chunk)
            if prev is not None and i >= prev + length and length >= len(found):
                found = chunk
            seen[chunk] = i
        if found:
            best = found
        else:
            break
    return best


def _jaccard(a: str, b: str, n: int = 2) -> float:
    left = set(char_ngrams(a, n))
    right = set(char_ngrams(b, n))
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def near_duplicate_sentence_hits(
    current: str,
    previous: list[str],
    *,
    threshold: float = 0.55,
    window: int = 6,
) -> int:
    prior_sents: list[str] = []
    for text in previous[-window:]:
        prior_sents.extend(sentences(text))
    hits = 0
    for sent in sentences(current):
        for old in prior_sents:
            score = max(
                SequenceMatcher(None, normalize_cjk(sent), normalize_cjk(old)).ratio(),
                _jaccard(sent, old),
            )
            if score >= threshold:
                hits += 1
                break
    return hits


def paragraph_near_duplicate_ratio(texts: list[str], *, threshold: float = 0.72) -> float:
    if len(texts) < 2:
        return 0.0
    hits = 0
    pairs = 0
    for i, current in enumerate(texts):
        for prev in texts[:i]:
            pairs += 1
            score = SequenceMatcher(None, normalize_cjk(current), normalize_cjk(prev)).ratio()
            if score >= threshold:
                hits += 1
    return hits / pairs if pairs else 0.0


def assistant_boundary_diversity(
    openings: list[str], closings: list[str]
) -> dict[str, float]:
    def _div(items: list[str]) -> float:
        clean = [normalize_cjk(x)[:8] for x in items if x and x.strip()]
        if not clean:
            return 1.0
        return len(set(clean)) / len(clean)

    return {"opening": _div(openings), "closing": _div(closings)}


def low_info_followup(user_text: str) -> str:
    blob = re.sub(r"[。．.！!？?…~～、,，]+", "", normalize_cjk(user_text))
    catalog = {re.sub(r"[。．.！!？?…~～、,，]+", "", normalize_cjk(x)) for x in _LOW_INFO}
    catalog.update({"然后呢", "是吗", "继续", "好的"})
    if blob in catalog:
        return "low_info"
    if len(blob) <= 2 and blob in {"嗯", "好", "哦", "喔"}:
        return "low_info"
    return "substantive"


def classify_followup(
    assistant_text: str,
    *,
    user_was_low_info: bool,
    previous: list[str] | None = None,
) -> str:
    if not user_was_low_info:
        return "n/a"
    sents = sentences(assistant_text)
    if not sents:
        return "repeat"
    if all(s.endswith("？") or s.endswith("?") for s in sents):
        return "question_only"
    if previous and near_duplicate_sentence_hits(
        assistant_text, previous, threshold=0.72
    ):
        return "repeat"
    return "new_event"


def summarize_run(rows: list[dict[str, Any]]) -> dict[str, Any]:
    contents = [str(r.get("content") or "") for r in rows]
    openings = [sentences(c)[0][:12] if sentences(c) else "" for c in contents]
    closings = [sentences(c)[-1][-12:] if sentences(c) else "" for c in contents]
    blob = "".join(contents)
    tokens = [float(r.get("completion_tokens") or 0) for r in rows]
    ttfts = [float(r["ttft_s"]) for r in rows if r.get("ttft_s") is not None]
    decodes = [float(r["decode_tok_s"]) for r in rows if r.get("decode_tok_s")]
    cache_hits = []
    prompts: list[int] = []
    for r in rows:
        prompt = float(r.get("prompt_tokens") or 0)
        cached = float(r.get("cached_tokens") or 0)
        prompts.append(int(prompt))
        cache_hits.append((cached / prompt) if prompt else 0.0)
    bounds = assistant_boundary_diversity(openings, closings)
    low_info_q = sum(1 for r in rows if r.get("followup_class") == "question_only")
    low_info_new = sum(1 for r in rows if r.get("followup_class") == "new_event")
    low_info_repeat = sum(1 for r in rows if r.get("followup_class") == "repeat")
    return {
        "turns": len(rows),
        "exact_duplicate_sentence_ratio": exact_duplicate_sentence_ratio(contents),
        "normalized_duplicate_sentence_ratio": normalized_duplicate_sentence_ratio(contents),
        "repeated_3gram": repeated_ngram_ratio(blob, 3),
        "repeated_4gram": repeated_ngram_ratio(blob, 4),
        "repeated_5gram": repeated_ngram_ratio(blob, 5),
        "longest_repeated_substring": longest_repeated_substring(blob),
        "paragraph_near_duplicate_ratio": paragraph_near_duplicate_ratio(contents),
        "opening_diversity": bounds["opening"],
        "closing_diversity": bounds["closing"],
        "avg_response_tokens": (sum(tokens) / len(tokens)) if tokens else 0.0,
        "p50_response_tokens": _percentile(tokens, 50),
        "p95_response_tokens": _percentile(tokens, 95),
        "length_finish_count": sum(1 for r in rows if r.get("finish_reason") == "length"),
        "stop_finish_count": sum(1 for r in rows if r.get("finish_reason") == "stop"),
        "protocol_failure_count": sum(1 for r in rows if r.get("protocol_failure")),
        "repetition_guard_count": sum(1 for r in rows if r.get("repetition_guard")),
        "ttft_p50": _percentile(ttfts, 50),
        "ttft_p95": _percentile(ttfts, 95),
        "decode_tok_s_p50": _percentile(decodes, 50),
        "cache_hit_p50": _percentile(cache_hits, 50),
        "prompt_tokens": prompts,
        "low_info_question_only": low_info_q,
        "low_info_new_event": low_info_new,
        "low_info_repeat": low_info_repeat,
        "median_ttft": median(ttfts) if ttfts else None,
    }
