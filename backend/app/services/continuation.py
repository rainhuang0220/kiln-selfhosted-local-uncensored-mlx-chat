"""Assistant continuation helpers.

mlx-lm 0.31.3 cannot express continue_final_message on /v1/chat/completions
(add_generation_prompt is hardcoded True). /v1/completions works with a
tokenizer-native prefix, but an exact prompt-cache hit empties insert_segments
and kills the generate thread. Dropping the last prompt token avoids that
exact hit; the model usually regenerates the token, so streamed deltas must
strip it before appending to the already-saved prefix.
"""

from __future__ import annotations

from collections.abc import Callable


def shorten_until_unused(
    prompt: str,
    *,
    encode: Callable[[str], list[int]],
    decode: Callable[[list[int]], str],
    used: list[str] | tuple[str, ...] | None = None,
    min_keep: int = 8,
) -> tuple[str, str]:
    """Drop at least one token, then more if this prefix was already sent.

    mlx-lm 0.31.3 dies on an exact prompt-cache hit. A second Continue with
    the same dropped prefix is that exact hit. A seen unshortened prompt
    (guard-cut back to where an earlier hop ended) was cached minus its last
    token, so its one-token drop counts as seen too.
    """
    ids = list(encode(prompt))
    if len(ids) < 2:
        return prompt, ""
    seen = set(used or [])
    # The cache is keyed by token ids: a sent prompt and that prompt minus its last
    # token. A differently spelled string can still re-encode onto either key.
    seen_ids: set[tuple[int, ...]] = set()
    for text in seen:
        sent = tuple(encode(text))
        seen_ids.update((sent, sent[:-1]))

    def cached(text: str) -> bool:
        return text in seen or tuple(encode(text)) in seen_ids

    max_drop = max(1, len(ids) - min_keep)
    drop_n = min(2, max_drop) if prompt in seen else 1
    trimmed = decode(ids[:-drop_n])
    tail = decode(ids[-drop_n:])
    while cached(trimmed) and drop_n < max_drop:
        drop_n += 1
        trimmed = decode(ids[:-drop_n])
        tail = decode(ids[-drop_n:])
    return trimmed, tail


def continue_assistant_message(content: str, reasoning: str) -> dict[str, str]:
    """Last assistant message when visible text already exists.

    Official Qwen template closes reasoning_content with </think>. Mid-think
    (reasoning only) must use the official thinking generation prefix instead.
    """
    asst: dict[str, str] = {"role": "assistant", "content": content}
    if reasoning:
        asst["reasoning_content"] = reasoning
    return asst


def drop_last_token(
    prompt: str,
    *,
    encode: Callable[[str], list[int]],
    decode: Callable[[list[int]], str],
) -> tuple[str, str]:
    ids = list(encode(prompt))
    if len(ids) < 2:
        return prompt, ""
    return decode(ids[:-1]), decode([ids[-1]])


def strip_regenerated_tail(generated: str, dropped_tail: str) -> str:
    if dropped_tail and generated.startswith(dropped_tail):
        return generated[len(dropped_tail) :]
    return generated


_ECHO_BREAKS = set("。！？!?…」』”\n")


class EchoSuppressor:
    """Hold streamed text while it reprints the previous assistant reply.

    After a length-cut reply, a short cue like 继续 often makes the model
    retype that reply before writing anything new. Whole copied sentences
    are dropped; a sentence that starts copied but diverges is kept whole.
    """

    def __init__(self, previous: str, *, min_match: int = 16):
        self.previous = previous or ""
        self.min_match = min_match
        self._held = ""
        self._done = not self.previous

    def _cut(self, matched: int) -> str:
        if matched < self.min_match:
            return self._held
        cut = 0
        for i in range(matched - 1, -1, -1):
            if self._held[i] in _ECHO_BREAKS:
                cut = i + 1
                break
        return self._held[cut:].lstrip() if cut else self._held

    def feed(self, text: str) -> str:
        if self._done or not text:
            return text
        self._held += text
        n = min(len(self._held), len(self.previous))
        matched = 0
        while matched < n and self._held[matched] == self.previous[matched]:
            matched += 1
        if matched == len(self._held) and matched < len(self.previous):
            return ""
        if matched == len(self.previous):
            rest = self._held[matched:].lstrip()
            if not rest:
                return ""
            self._done = True
            self._held = ""
            return rest
        self._done = True
        out = self._cut(matched)
        self._held = ""
        return out

    def flush(self) -> str:
        if self._done:
            return ""
        self._done = True
        matched = len(self._held)
        out = "" if matched >= self.min_match and self.previous.startswith(self._held) else self._held
        self._held = ""
        return out


class TailStripper:
    def __init__(self, dropped_tail: str):
        self.pending = dropped_tail or ""
        self._held = ""

    def feed(self, text: str) -> str:
        if not text or not self.pending:
            return text
        if text.startswith(self.pending):
            out = text[len(self.pending) :]
            self.pending = ""
            self._held = ""
            return out
        if self.pending.startswith(text):
            self._held += text
            self.pending = self.pending[len(text) :]
            return ""
        out = self._held + text
        self.pending = ""
        self._held = ""
        return out
