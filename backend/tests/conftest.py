from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.db import init_db
from app.main import create_app
from app.providers.base import ChatChunk, ChatRequest, ChatResult
from app.services.chat import ChatService
from app.services.memory import MemoryService
from app.services.tokens import TokenEstimator


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.calls: list[ChatRequest] = []

    def context_window(self) -> int:
        return 262144

    def default_model(self) -> str:
        return "qwen3.8-27b"

    async def health(self) -> bool:
        return True

    async def complete(self, request: ChatRequest) -> ChatResult:
        self.calls.append(request)
        last = request.messages[-1]["content"] if request.messages else ""
        return ChatResult(
            id="chatcmpl-fake",
            model="qwen3.8-27b",
            content=f"echo:{last}",
            reasoning="think",
            finish_reason="stop",
            prompt_tokens=12,
            completion_tokens=4,
            cached_tokens=0,
            usage_source="upstream",
        )

    async def stream(self, request: ChatRequest):
        self.calls.append(request)
        last = request.messages[-1]["content"] if request.messages else ""
        yield ChatChunk(id="chatcmpl-fake", model="qwen3.8-27b", delta_reasoning="think")
        yield ChatChunk(id="chatcmpl-fake", model="qwen3.8-27b", delta_content="echo:")
        yield ChatChunk(id="chatcmpl-fake", model="qwen3.8-27b", delta_content=last)
        yield ChatChunk(
            id="chatcmpl-fake",
            model="qwen3.8-27b",
            finish_reason="stop",
            prompt_tokens=12,
            completion_tokens=4,
            cached_tokens=0,
        )

    async def complete_after_think(self, request: ChatRequest, reasoning: str, max_tokens: int) -> ChatResult:
        self.calls.append(request)
        return ChatResult(
            id="chatcmpl-fake",
            model="qwen3.8-27b",
            content="answer-after-think",
            reasoning="",
            finish_reason="stop",
            prompt_tokens=12,
            completion_tokens=4,
            cached_tokens=0,
            usage_source="upstream",
        )

    async def stream_after_think(self, request: ChatRequest, reasoning: str, max_tokens: int):
        self.calls.append(request)
        yield ChatChunk(id="chatcmpl-fake", model="qwen3.8-27b", delta_content="answer-after-think")
        yield ChatChunk(
            id="chatcmpl-fake",
            model="qwen3.8-27b",
            finish_reason="stop",
            prompt_tokens=12,
            completion_tokens=4,
            cached_tokens=0,
        )


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    db = tmp_path / "chat.db"
    init_db(str(db))
    return Settings(
        sqlite_path=str(db),
        mlx_base_url="http://127.0.0.1:8081",
        model_path=str(Path(__file__).resolve().parents[3] / "qwen3.8-27b"),
        app_password="",
    )


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def chat_service(tmp_settings: Settings, fake_provider: FakeProvider) -> ChatService:
    from app import db as dbmod

    dbmod._local.conn = dbmod._connect(tmp_settings.sqlite_path)
    tok = TokenEstimator(tmp_settings.model_path)
    return ChatService(tmp_settings, fake_provider, tok, MemoryService())


@pytest.fixture
def client(tmp_settings: Settings, chat_service: ChatService):
    from starlette.testclient import TestClient

    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app) as c:
        yield c
