"""Chat worker lifecycle: park during heavy local generation, then restore."""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Awaitable

from app.config import Settings

RUNNING = "running"
PARKING = "parking"
PARKED = "parked"
RESTORING = "restoring"
RECOVERY_FAILED = "recovery_failed"

UNAVAILABLE = {PARKING, PARKED, RESTORING, RECOVERY_FAILED}

PARKED_MESSAGE = (
    "Chat is temporarily unavailable while local video generation is using system memory."
)


class ChatLifecycle:
    def __init__(
        self,
        settings: Settings,
        park_fn: Callable[[Settings], Awaitable[None] | None] | None = None,
        restore_fn: Callable[[Settings], Awaitable[None] | None] | None = None,
    ):
        self.settings = settings
        self.state = RUNNING
        self.reason: str | None = None
        self._lock = asyncio.Lock()
        self._park_fn = park_fn
        self._restore_fn = restore_fn

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "reason": self.reason,
            "retryable": self.state != RECOVERY_FAILED,
            "message": PARKED_MESSAGE if self.state in UNAVAILABLE else None,
        }

    def is_unavailable(self) -> bool:
        return self.state in UNAVAILABLE

    async def park(self, reason: str | None = None) -> None:
        async with self._lock:
            if self.state == PARKED:
                self.reason = reason or self.reason
                return
            self.state = PARKING
            self.reason = reason
            try:
                await self._call(self._park_fn, default="park")
                self.state = PARKED
            except Exception:
                self.state = RECOVERY_FAILED
                raise

    async def restore(self) -> None:
        async with self._lock:
            if self.state == RUNNING:
                return
            self.state = RESTORING
            try:
                await self._call(self._restore_fn, default="restore")
                self.state = RUNNING
                self.reason = None
            except Exception:
                self.state = RECOVERY_FAILED
                raise

    async def _call(self, fn, *, default: str) -> None:
        if fn is None:
            from app.services import media_runtime

            sync = media_runtime.pause_mlx if default == "park" else media_runtime.restore_mlx
            await asyncio.to_thread(sync, self.settings)
            return
        result = fn(self.settings)
        if asyncio.iscoroutine(result):
            await result


def parked_http_body() -> dict[str, Any]:
    return {
        "code": "CHAT_MODEL_PARKED",
        "message": PARKED_MESSAGE,
        "retryable": True,
        "error": {
            "message": PARKED_MESSAGE,
            "type": "service_unavailable",
            "code": "CHAT_MODEL_PARKED",
            "retryable": True,
        },
    }
