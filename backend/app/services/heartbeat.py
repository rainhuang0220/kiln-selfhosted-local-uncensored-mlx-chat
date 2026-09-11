"""Application-level SSE heartbeats that do not cancel the provider generator."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator


async def iterate_with_heartbeats(
    agen: AsyncIterator[dict[str, Any]],
    interval_s: float,
    *,
    ping: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    interval = float(interval_s) if interval_s and float(interval_s) > 0 else 15.0
    payload = ping or {"event": "ping", "data": {"ok": True}}
    pending = asyncio.create_task(agen.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield payload
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            yield event
            pending = asyncio.create_task(agen.__anext__())
    finally:
        if not pending.done():
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
        closer = getattr(agen, "aclose", None)
        if closer is not None:
            try:
                await closer()
            except (asyncio.CancelledError, StopAsyncIteration, RuntimeError):
                pass
