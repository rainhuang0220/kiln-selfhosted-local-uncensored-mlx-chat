from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class MemoryRecord:
    id: str
    memory_type: str
    key: str | None
    content: str
    importance: float
    confidence: float = 0.5
    status: str = "active"


class MemoryProvider(Protocol):
    def save(self, record: MemoryRecord) -> MemoryRecord: ...
    def search(self, query: str, *, limit: int = 20, budget_tokens: int = 512) -> list[MemoryRecord]: ...
    def delete(self, memory_id: str) -> bool: ...
    def update(self, memory_id: str, **fields: object) -> MemoryRecord | None: ...
    def summarize(self, texts: list[str], *, max_chars: int = 800) -> str: ...
    def retrieve_for_prompt(self, query: str, budget_tokens: int) -> list[MemoryRecord]: ...
    def fence(self, items: list[MemoryRecord]) -> str | None: ...
