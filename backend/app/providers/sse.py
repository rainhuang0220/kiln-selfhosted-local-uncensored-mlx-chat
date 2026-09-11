"""mlx-lm 0.31.3 SSE adapter. Do not treat HTTP EOF as a normal stop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

FrameKind = Literal["json", "done", "keepalive", "malformed"]


@dataclass(frozen=True)
class SseFrame:
    kind: FrameKind
    payload: dict[str, Any] | None = None
    raw: str = ""


def parse_sse_line(line: str) -> SseFrame | None:
    text = line.strip("\r")
    if not text:
        return None
    if text.startswith(":"):
        return SseFrame(kind="keepalive", raw=text[1:].strip())
    if not text.startswith("data:"):
        return None
    payload = text[5:].strip()
    if payload == "[DONE]":
        return SseFrame(kind="done", raw=payload)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return SseFrame(kind="malformed", raw=payload)
    if not isinstance(data, dict):
        return SseFrame(kind="malformed", raw=payload)
    return SseFrame(kind="json", payload=data, raw=payload)


async def iter_sse_frames(chunks: AsyncIterator[str]) -> AsyncIterator[SseFrame]:
    buffer = ""
    async for raw in chunks:
        buffer += raw
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            frame = parse_sse_line(line)
            if frame is not None:
                yield frame
    tail = parse_sse_line(buffer)
    if tail is not None:
        yield tail
