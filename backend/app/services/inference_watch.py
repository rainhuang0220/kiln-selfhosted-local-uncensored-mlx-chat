"""Transport success is not evidence that generation works.

A fresh process stays UNVERIFIED until a real generation succeeds.
BUSY is a queue fact and never means the generation thread died.
"""

from __future__ import annotations

import time
from typing import Any, Callable


DEFAULT_EVIDENCE_TTL_MS = 15 * 60 * 1000


def _clock() -> int:
    return int(time.time() * 1000)


class InferenceWatch:
    def __init__(self, *, ttl_ms: int = DEFAULT_EVIDENCE_TTL_MS, now: Callable[[], int] | None = None):
        self.ttl_ms = ttl_ms
        self._now = now or _clock
        self._timeouts = 0
        self._failures = 0
        self._last_error: str | None = None
        self._last_verified_at: int | None = None
        self._method: str | None = None
        self._degraded = False
        self._failed = False

    def note_success(self, method: str = "user_generation") -> None:
        self._timeouts = 0
        self._failures = 0
        self._last_error = None
        self._degraded = False
        self._failed = False
        self._last_verified_at = self._now()
        self._method = method

    def note_timeout(self, message: str | None = None) -> None:
        self._timeouts += 1
        self._failures += 1
        self._last_error = message or "mlx timeout"
        self._degraded = True
        if self._timeouts >= 3:
            self._failed = True

    def note_failure(self, message: str | None = None) -> None:
        self._failures += 1
        self._last_error = message or "generation failed"
        self._degraded = True
        if self._failures >= 3:
            self._failed = True

    def note_thread_dead(self, message: str | None = None) -> None:
        self._failures += 1
        self._last_error = message or "generation thread is not alive"
        self._degraded = True
        self._failed = True

    def note_unloaded(self) -> None:
        self._last_error = "model unloaded"
        self._degraded = True
        self._failed = True

    def capability(self, *, busy: bool) -> str:
        if busy:
            return "BUSY"
        if self._failed:
            return "FAILED"
        if self._degraded:
            return "DEGRADED"
        if self._evidence_fresh():
            return "READY"
        return "UNVERIFIED"

    def snapshot(self) -> dict[str, Any]:
        verified = self._last_verified_at
        expires = None if verified is None else verified + self.ttl_ms
        cap = self.capability(busy=False)
        return {
            "ready": cap == "READY",
            "consecutive_timeouts": self._timeouts,
            "last_error": self._last_error,
            "last_verified_at": verified,
            "verification_method": self._method,
            "evidence_expires_at": expires,
            "capability": cap,
        }

    def _evidence_fresh(self) -> bool:
        if self._last_verified_at is None or self._degraded or self._failed:
            return False
        return self._now() - self._last_verified_at <= self.ttl_ms


def recovery_action(*, capability: str, busy: bool) -> str | None:
    """Name the isolated recovery step. Callers must not target the live MLX pid."""
    if busy or capability != "FAILED":
        return None
    return "restart_backend"
