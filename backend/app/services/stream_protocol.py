"""Explicit generation terminal states. Never infer a normal stop from silence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TerminalState(str, Enum):
    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETED_STOP = "completed_stop"
    COMPLETED_LENGTH = "completed_length"
    INTERRUPTED_USER = "interrupted_user"
    INTERRUPTED_TRANSPORT = "interrupted_transport"
    UPSTREAM_PROTOCOL_ERROR = "upstream_protocol_error"
    TIMEOUT = "timeout"
    GENERATION_ERROR = "generation_error"
    REPETITION_GUARD = "repetition_guard"
    UNKNOWN_TERMINAL = "unknown_terminal"


COMPLETE_STATES = {TerminalState.COMPLETED_STOP, TerminalState.COMPLETED_LENGTH}
INCOMPLETE_STATES = {
    TerminalState.INTERRUPTED_USER,
    TerminalState.INTERRUPTED_TRANSPORT,
    TerminalState.UPSTREAM_PROTOCOL_ERROR,
    TerminalState.TIMEOUT,
    TerminalState.GENERATION_ERROR,
    TerminalState.REPETITION_GUARD,
    TerminalState.UNKNOWN_TERMINAL,
}

# mlx-lm 0.31.3 writes a final choice with finish_reason, optional usage, then `data: [DONE]`.
# Generator exhaustion after HTTP EOF is NOT that contract.
RELIABLE_UPSTREAM_FINISH = {"stop", "length", "tool_calls"}


class StreamProtocolError(Exception):
    """Upstream SSE violated the expected mlx-lm contract."""


@dataclass
class StreamLedger:
    saw_done_wire: bool = False
    saw_finish_reason: bool = False
    finish_reason: str | None = None
    malformed_frames: int = 0
    provider_protocol_closed: bool = False
    http_eof: bool = False
    cancelled: bool = False
    repetition_guard: bool = False
    exception: BaseException | None = None
    had_output: bool = False
    thinking_tokens: int = 0
    visible_tokens: int = 0
    first_visible_ms: int | None = None
    first_any_ms: int | None = None
    started_ms: int = 0
    ended_ms: int = 0
    extras: dict[str, Any] = field(default_factory=dict)

    def observe_finish(self, reason: str | None) -> None:
        if not reason:
            return
        self.saw_finish_reason = True
        self.finish_reason = reason

    def observe_done_wire(self) -> None:
        self.saw_done_wire = True
        self.provider_protocol_closed = True

    def classify(self) -> TerminalState:
        if self.cancelled:
            return TerminalState.INTERRUPTED_USER
        if self.repetition_guard:
            return TerminalState.REPETITION_GUARD
        if isinstance(self.exception, TimeoutError):
            return TerminalState.TIMEOUT
        if isinstance(self.exception, ConnectionError):
            return TerminalState.INTERRUPTED_TRANSPORT
        if self.exception is not None:
            return TerminalState.GENERATION_ERROR
        if self.malformed_frames and not self.saw_finish_reason and not self.saw_done_wire:
            return TerminalState.UPSTREAM_PROTOCOL_ERROR
        if self.saw_finish_reason and self.finish_reason == "length":
            if self.saw_done_wire or self.provider_protocol_closed:
                return TerminalState.COMPLETED_LENGTH
            if self.http_eof:
                return TerminalState.INTERRUPTED_TRANSPORT
            return TerminalState.UNKNOWN_TERMINAL
        if self.saw_finish_reason and self.finish_reason in RELIABLE_UPSTREAM_FINISH:
            if self.saw_done_wire or self.provider_protocol_closed:
                return TerminalState.COMPLETED_STOP
            if self.http_eof:
                return TerminalState.INTERRUPTED_TRANSPORT
            return TerminalState.UNKNOWN_TERMINAL
        if self.saw_done_wire and not self.saw_finish_reason:
            return TerminalState.UPSTREAM_PROTOCOL_ERROR
        if self.http_eof and not self.saw_done_wire:
            return TerminalState.INTERRUPTED_TRANSPORT
        return TerminalState.UNKNOWN_TERMINAL

    def message_status(self, state: TerminalState | None = None) -> str:
        resolved = state or self.classify()
        if resolved in COMPLETE_STATES:
            return "complete"
        if resolved is TerminalState.INTERRUPTED_USER:
            return "cancelled"
        return "error"

    def stored_finish_reason(self, state: TerminalState | None = None) -> str:
        resolved = state or self.classify()
        if resolved is TerminalState.COMPLETED_STOP:
            return self.finish_reason or "stop"
        if resolved is TerminalState.COMPLETED_LENGTH:
            return "length"
        if resolved is TerminalState.INTERRUPTED_USER:
            return "abort"
        return resolved.value

    def incomplete(self, state: TerminalState | None = None) -> bool:
        return (state or self.classify()) in INCOMPLETE_STATES

    def to_metrics(self, *, prompt_tokens: int, completion_tokens: int, cached_tokens: int) -> dict[str, Any]:
        total_s = max(0, self.ended_ms - self.started_ms) / 1000 if self.ended_ms else None
        ttft_s = None
        visible_mark = self.first_visible_ms if self.first_visible_ms is not None else self.first_any_ms
        if visible_mark is not None and self.started_ms:
            ttft_s = max(0, visible_mark - self.started_ms) / 1000
        decode_s = None
        if self.first_any_ms is not None and self.ended_ms and self.ended_ms > self.first_any_ms:
            decode_s = (self.ended_ms - self.first_any_ms) / 1000
        return {
            "ttft_ms": int(ttft_s * 1000) if ttft_s is not None else None,
            "total_latency_ms": int(total_s * 1000) if total_s is not None else None,
            "effective_output_tokens_per_sec": (
                completion_tokens / total_s if total_s and completion_tokens else None
            ),
            "decode_tokens_per_sec": (
                completion_tokens / decode_s if decode_s and completion_tokens else None
            ),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cached_tokens": cached_tokens,
            "cache_hit_ratio": (cached_tokens / prompt_tokens) if prompt_tokens else None,
            "thinking_tokens": self.thinking_tokens,
            "visible_tokens": self.visible_tokens,
            "malformed_sse_frames": self.malformed_frames,
            "saw_done_wire": self.saw_done_wire,
            "saw_finish_reason": self.saw_finish_reason,
            "http_eof": self.http_eof,
        }


def classify_non_stream(
    *,
    finish_reason: str | None,
    error: BaseException | None = None,
    cancelled: bool = False,
) -> TerminalState:
    ledger = StreamLedger(
        saw_done_wire=True,
        provider_protocol_closed=True,
        saw_finish_reason=bool(finish_reason),
        finish_reason=finish_reason,
        exception=error,
        cancelled=cancelled,
    )
    return ledger.classify()
