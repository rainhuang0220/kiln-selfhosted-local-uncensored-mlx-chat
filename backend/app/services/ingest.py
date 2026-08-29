from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

Estimate = Callable[[str], int]

FILE_MARK = "\n# File:"
_TERM = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]{2,}")


@dataclass(frozen=True)
class PackedDocument:
    text: str
    applied: bool
    original_tokens: int
    kept_tokens: int
    chunks_total: int
    chunks_kept: int


def fast_token_guess(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    if cjk * 2 >= len(text):
        return max(1, len(text))
    return max(1, len(text.encode("utf-8")) // 4)


def split_query_and_body(content: str) -> tuple[str, str]:
    if FILE_MARK in content:
        i = content.find(FILE_MARK)
        return content[:i].strip(), content[i:].lstrip()
    return "", content


def split_chunks(text: str, chunk_chars: int = 1600, overlap_chars: int = 80) -> list[str]:
    if not text:
        return []
    lines = text.split("\n")
    chunks: list[str] = []
    buf: list[str] = []
    n = 0

    def flush() -> None:
        nonlocal buf, n
        if buf:
            chunks.append("\n".join(buf))
            keep: list[str] = []
            k = 0
            for prev in reversed(buf):
                if k + len(prev) + 1 > overlap_chars:
                    break
                keep.append(prev)
                k += len(prev) + 1
            buf = list(reversed(keep))
            n = sum(len(x) + 1 for x in buf)

    for line in lines:
        if len(line) > chunk_chars:
            flush()
            buf, n = [], 0
            for i in range(0, len(line), chunk_chars):
                chunks.append(line[i : i + chunk_chars])
            continue
        extra = len(line) + 1
        if buf and n + extra > chunk_chars:
            flush()
        buf.append(line)
        n += extra
    if buf:
        chunks.append("\n".join(buf))
    return [c for c in chunks if c.strip()]


def _terms(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TERM.finditer(text[:8000])}


def _score(chunk: str, query_terms: set[str]) -> int:
    if not query_terms:
        return 0
    return sum(1 for t in _terms(chunk) if t in query_terms)


def pack_document(
    text: str,
    budget: int,
    estimate: Estimate,
    query: str = "",
) -> PackedDocument:
    if not text:
        return PackedDocument("", False, 0, 0, 0, 0)
    orig = estimate(text) if len(text) < 200_000 else fast_token_guess(text)
    if budget <= 0:
        return PackedDocument(
            "<document packed=\"true\" original_tokens=\"%d\" kept_tokens=\"0\" />" % orig,
            True,
            orig,
            0,
            0,
            0,
        )
    if orig <= budget:
        return PackedDocument(text, False, orig, orig, 1, 1)

    chunks = split_chunks(text)
    if not chunks:
        return PackedDocument(text[: max(1, budget * 2)], True, orig, budget, 1, 1)

    query_terms = _terms(query or text[:800])
    head, tail = chunks[0], chunks[-1]
    middle_idx = list(range(1, max(1, len(chunks) - 1)))
    middle_idx.sort(key=lambda i: _score(chunks[i], query_terms), reverse=True)

    selected: dict[int, str] = {0: head}
    if len(chunks) > 1:
        selected[len(chunks) - 1] = tail

    def render(chosen: dict[int, str]) -> str:
        order = sorted(chosen)
        parts: list[str] = []
        prev = -1
        for i in order:
            if prev != -1 and i > prev + 1:
                parts.append("\n\n[... omitted ...]\n\n")
            parts.append(chosen[i])
            prev = i
        body = "".join(parts)
        return (
            f"<document packed=\"true\" original_tokens=\"{orig}\" "
            f"chunks_kept=\"{len(chosen)}\" chunks_total=\"{len(chunks)}\">\n"
            f"{body}\n</document>"
        )

    kept = render(selected)
    if estimate(kept) > budget:
        lo, hi = 16, max(len(head), len(tail), 16)
        best: dict[int, str] = {0: head[:16]}
        best_text = render(best)
        while lo <= hi:
            mid = (lo + hi) // 2
            trial = {0: head[:mid]}
            if len(chunks) > 1:
                trial[len(chunks) - 1] = tail[-mid:]
            cand = render(trial)
            if estimate(cand) <= budget:
                best, best_text = trial, cand
                lo = mid + 1
            else:
                hi = mid - 1
        selected, kept = best, best_text

    for i in middle_idx:
        if i in selected:
            continue
        trial = dict(selected)
        trial[i] = chunks[i]
        cand = render(trial)
        if estimate(cand) <= budget:
            selected = trial
            kept = cand
        elif estimate(kept) >= budget:
            break

    return PackedDocument(
        kept,
        True,
        orig,
        estimate(kept) if len(kept) < 200_000 else fast_token_guess(kept),
        len(chunks),
        len(selected),
    )


def pack_user_message(content: str, budget: int, estimate: Estimate) -> PackedDocument:
    query, body = split_query_and_body(content)
    target = body if query else content
    qtok = estimate(query) if query else 0
    room = max(64, budget - qtok - 48)
    packed = pack_document(target, room, estimate, query=query or content[:400])
    if not packed.applied:
        return PackedDocument(content, False, packed.original_tokens, packed.kept_tokens, packed.chunks_total, packed.chunks_kept)
    text = f"{query}\n\n{packed.text}".strip() if query else packed.text
    return PackedDocument(
        text,
        True,
        packed.original_tokens,
        estimate(text) if len(text) < 200_000 else packed.kept_tokens + qtok,
        packed.chunks_total,
        packed.chunks_kept,
    )


def extract_text_bytes(data: bytes, name: str) -> str:
    sample = data[:4096]
    if b"\x00" in sample:
        raise ValueError(f"{name} looks binary; attach text, markdown, or code")
    return data.decode("utf-8", errors="replace")
