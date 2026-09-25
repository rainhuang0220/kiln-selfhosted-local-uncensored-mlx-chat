"""Route a long document without pretending a subset is the original.

The archived text is immutable. Prefix-cache identity covers model, revision,
template, and the thinking flag so a summary rewrite cannot reuse another prefix.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable

CountTokens = Callable[[str], int]

_VERBATIM_MARKS = ("逐字", "原文", "全文", "精确", "代码", "引用位置")


@dataclass(frozen=True)
class ArchivedDocument:
    doc_id: str
    sha256: str
    text: str


@dataclass(frozen=True)
class Citation:
    chunk_id: str
    start: int
    end: int
    text: str


@dataclass
class RouteResult:
    mode: str
    archive: ArchivedDocument
    model_text: str | None
    original_chars: int
    served_chars: int
    silent_truncation: bool
    represents_full_document: bool
    citations: list[Citation] = field(default_factory=list)


def describe_input(text: str, count_tokens: CountTokens) -> dict[str, int]:
    return {"chars": len(text), "tokens": int(count_tokens(text))}


def cache_identity(*, model: str, revision: str, template: str, thinking: bool) -> str:
    raw = "\n".join((model, revision, template, "1" if thinking else "0"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _archive(text: str) -> ArchivedDocument:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ArchivedDocument(doc_id=digest[:16], sha256=digest, text=text)


def _chunks(doc: ArchivedDocument, chunk_chars: int) -> list[Citation]:
    step = max(1, chunk_chars)
    out: list[Citation] = []
    start = 0
    while start < len(doc.text):
        end = min(len(doc.text), start + step)
        piece = doc.text[start:end]
        out.append(
            Citation(
                chunk_id=f"{doc.doc_id}:{start}:{end}",
                start=start,
                end=end,
                text=piece,
            )
        )
        start = end
    return out


def _wants_verbatim(question: str) -> bool:
    return any(mark in (question or "") for mark in _VERBATIM_MARKS)


def _overlap(question: str, chunk: str) -> int:
    if len(question) < 2:
        return 1 if question and question in chunk else 0
    hits = 0
    for index in range(len(question) - 1):
        gram = question[index : index + 2]
        if gram.strip() and gram in chunk:
            hits += 1
    return hits


def route_document(
    *,
    text: str,
    question: str,
    token_budget: int,
    count_tokens: CountTokens,
    reserved_output: int = 0,
    chunk_chars: int = 400,
) -> RouteResult:
    archive = _archive(text)
    original_chars = len(text)
    room = token_budget - max(0, reserved_output)
    if room > 0 and count_tokens(text) <= room:
        return RouteResult(
            mode="verbatim",
            archive=archive,
            model_text=text,
            original_chars=original_chars,
            served_chars=original_chars,
            silent_truncation=False,
            represents_full_document=True,
        )
    if _wants_verbatim(question):
        return RouteResult(
            mode="verbatim_exceeds_budget",
            archive=archive,
            model_text=None,
            original_chars=original_chars,
            served_chars=0,
            silent_truncation=False,
            represents_full_document=False,
        )
    chosen: list[Citation] = []
    used = 0
    ranked = sorted(_chunks(archive, chunk_chars), key=lambda item: _overlap(question, item.text), reverse=True)
    for chunk in ranked:
        if _overlap(question, chunk.text) <= 0:
            continue
        cost = count_tokens(chunk.text)
        if used + cost > room:
            continue
        chosen.append(chunk)
        used += cost
    chosen.sort(key=lambda item: item.start)
    model_text = "\n".join(item.text for item in chosen) if chosen else None
    return RouteResult(
        mode="retrieval",
        archive=archive,
        model_text=model_text,
        original_chars=original_chars,
        served_chars=len(model_text or ""),
        silent_truncation=False,
        represents_full_document=False,
        citations=chosen,
    )
