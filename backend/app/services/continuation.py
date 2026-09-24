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
    the same dropped prefix is that exact hit.
    """
    ids = list(encode(prompt))
    if len(ids) < 2:
        return prompt, ""
    seen = set(used or [])
    drop_n = 1
    max_drop = max(1, len(ids) - min_keep)
    trimmed = decode(ids[:-1])
    tail = decode(ids[-1:])
    while trimmed in seen and drop_n < max_drop:
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
