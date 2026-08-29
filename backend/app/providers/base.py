from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol


@dataclass
class ChatRequest:
    messages: list[dict[str, Any]]
    temperature: float = 1.0
    top_p: float = 0.95
    top_k: int = 20
    max_tokens: int = 8192
    stop: list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    enable_thinking: bool = True
    reasoning_effort: str = "medium"
    preserve_thinking: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResult:
    id: str
    model: str
    content: str
    reasoning: str
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    usage_source: str
    raw: dict[str, Any] | None = None


@dataclass
class ChatChunk:
    id: str
    model: str
    delta_content: str | None = None
    delta_reasoning: str | None = None
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    keepalive: str | None = None


class ChatProvider(Protocol):
    name: str

    def context_window(self) -> int: ...
    def default_model(self) -> str: ...
    async def health(self) -> bool: ...
    async def complete(self, request: ChatRequest) -> ChatResult: ...
    def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]: ...
