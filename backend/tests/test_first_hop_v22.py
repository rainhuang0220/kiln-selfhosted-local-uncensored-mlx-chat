"""V22: service requirements on the first immersive hop + 45s first-token idle."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from app.providers.base import ChatChunk

JIAOZHI = Path(__file__).resolve().parents[2] / "docs" / "test" / "多人物交织场景_输入.md"
SHARED = (Path(__file__).parent / "fixtures" / "preset_shared_scene_ten.txt").read_text("utf-8")
# Stage A merges a first-person liking into me.explicit_prefs; the rules draft leaves it 暂无.
STAGE_A_PREF = "喜欢那种被注视的紧张"
OFFSTAGE = ("陆遥", "沈乔", "小学三年级", "阁楼", "唐宁", "林见", "何冉")


def _bound_jiaozhi_ir() -> dict:
    from app.services.context_compiler.compiler import compile_context
    from app.services.context_presets import preview_preset

    source = JIAOZHI.read_text("utf-8")
    draft = preview_preset(source)
    assert STAGE_A_PREF in source
    draft["me"]["explicit_prefs"] = STAGE_A_PREF
    ir = compile_context(source, draft)
    ir["preference_field_at_compile"] = STAGE_A_PREF
    return ir


def test_h1_bare_hello_parlor_pin_only():
    from app.services.context_compiler import route_context

    hop = route_context(_bound_jiaozhi_ir(), "你好")
    assert hop.intent == "roleplay"
    fence = hop.fence
    assert fence.splitlines()[-1].startswith("此刻现场：")
    assert "技师" in fence
    assert "接待室" in fence
    assert "do_not_literalize" not in fence
    assert "<service_requirements" not in fence
    for token in OFFSTAGE:
        assert token not in fence
    assert "以下内容仅作为参考" not in fence
    assert "参考事件" not in fence


def test_h1b_shared_scene_does_not_invent_bracket_preferences():
    from app.services.context_compiler import route_context
    from app.services.context_presets import preview_preset

    hop = route_context(preview_preset(SHARED)["context_ir"], "你好")
    assert hop.fence.splitlines()[-1].startswith("此刻现场：")
    assert "慢节奏" not in hop.fence
    for name in ("顾遥", "祁律", "褚衡"):
        assert name not in hop.fence


def test_h1c_nonbracket_preferences_do_not_become_rules():
    from app.services.context_compiler import route_context

    ir = {
        "version": 2,
        "persona": {"role": "风俗店技师", "rules": ["先确认力度再开始"]},
        "user_avatar": {"identity": "我是顾客"},
        "current_scene": "接待室矮桌上两杯水。",
        "entities": [{"name": "陆遥", "identity": "姐姐"}, {"name": "顾遥", "identity": "室友"}],
        "segments": [
            {"type": "USER_PREFERENCE", "text": "明确偏好：说话慢一点，多问我的感受。", "scope": "live"},
            {"type": "USER_PREFERENCE", "text": "陆遥喜欢这样。", "scope": "reference"},
            {"type": "USER_PREFERENCE", "text": "小学的时候我就这样。", "scope": "reference"},
        ],
        "preferences": [
            {"content": "以下内容仅作为参考。", "do_not_literalize": True},
            {"content": "阁楼那晚的气氛。", "do_not_literalize": True},
            {"content": "说话慢一点，多问我的感受。", "do_not_literalize": True},
        ],
        "events": [{"order": 1, "actors": ["陆遥"], "description": "阁楼里谈了一夜"}],
        "preference_field_at_compile": "暂无",
    }
    block = route_context(ir, "你好").fence
    assert "先确认力度" not in block
    assert "说话慢一点" not in block
    for token in ("陆遥", "顾遥", "小学", "阁楼", "以下内容"):
        assert token not in block


def test_h2_fence_budget_281():
    from app.services.context_compiler import route_context

    ir = _bound_jiaozhi_ir()
    assert len(route_context(ir, "你好").fence) <= 281
    ir["persona"]["rules"] = [f"服务要求第{i}条：先问清楚再继续，语气放慢，不要跳过确认。" for i in range(40)]
    ir["preference_field_at_compile"] = "；".join(f"偏好{i}：短句、慢节奏、写呼吸" for i in range(40))
    fence = route_context(ir, "你好").fence
    assert len(fence) <= 281
    assert fence.splitlines()[-1].startswith("此刻现场：") and "接待室" in fence
    assert "服务要求第" not in fence


def test_h3_named_recall_isolated_bare_hello_clean():
    from app.services.context_compiler import route_context

    ir = _bound_jiaozhi_ir()
    recall = route_context(ir, "陆遥是谁")
    assert recall.intent == "recall"
    ref = recall.reference_fence or ""
    assert "陆遥" in ref
    for line in ref.splitlines():
        if line.startswith("参考事件"):
            assert "陆遥" in line
    assert "<service_requirements" not in recall.fence
    hello = route_context(ir, "你好").fence
    assert "陆遥" not in hello
    assert "参考事件" not in hello


class _TimedProvider:
    """Stub stream: optional delay before the first token, or never yields."""

    name = "timed"

    def __init__(self, *, first_delay_s: float, tokens: int = 3, raise_exc: Exception | None = None):
        self.first_delay_s = first_delay_s
        self.tokens = tokens
        self.raise_exc = raise_exc

    def context_window(self) -> int:
        return 262144

    def default_model(self) -> str:
        return "stub"

    async def health(self) -> bool:
        return True

    async def stream(self, request):
        if self.raise_exc is not None:
            raise self.raise_exc
        await asyncio.sleep(self.first_delay_s)
        for i in range(self.tokens):
            yield ChatChunk(id="stub", model="stub", delta_content=f"好{i}")
        yield ChatChunk(id="stub", model="stub", finish_reason="stop", prompt_tokens=4, completion_tokens=self.tokens)
        yield ChatChunk(id="stub", model="stub", wire_done=True)


async def _run(chat_service) -> tuple[list[dict], float]:
    started = time.monotonic()
    events = [
        event
        async for event in chat_service.chat(
            message="你好",
            conversation_id=None,
            stream=True,
            auto_continue=False,
            max_tokens=32,
        )
    ]
    return events, time.monotonic() - started


def _errors(events: list[dict]) -> list[str]:
    return [e["data"]["error"]["message"] for e in events if e.get("event") == "error"]


def test_idle_constants():
    from app.services.generation_errors import BETWEEN_TOKEN_IDLE_S, FIRST_TOKEN_IDLE_S

    assert FIRST_TOKEN_IDLE_S == 45.0
    assert BETWEEN_TOKEN_IDLE_S == 20.0


@pytest.fixture
def scaled_idle(monkeypatch):
    """Scale 45s / 20s by 1/100 so the stub timeline runs in under a second."""
    from app.services import chat as chat_mod

    monkeypatch.setattr(chat_mod, "FIRST_TOKEN_IDLE_S", 0.45)
    monkeypatch.setattr(chat_mod, "BETWEEN_TOKEN_IDLE_S", 0.20)
    return 0.01


@pytest.mark.asyncio
async def test_h4_first_token_at_30s_is_not_idle(chat_service, scaled_idle):
    chat_service.provider = _TimedProvider(first_delay_s=30 * scaled_idle)
    events, _ = await _run(chat_service)
    assert _errors(events) == []
    text = "".join(e["data"].get("content") or "" for e in events if e.get("event") == "delta")
    assert "好0" in text


@pytest.mark.asyncio
async def test_h5_silent_provider_surfaces_busy(chat_service, scaled_idle):
    from app.services.generation_errors import PROVIDER_BUSY

    chat_service.provider = _TimedProvider(first_delay_s=3600)
    events, elapsed = await asyncio.wait_for(_run(chat_service), timeout=5)
    errors = _errors(events)
    assert errors and all(msg == PROVIDER_BUSY for msg in errors)
    assert elapsed < 45 * scaled_idle * 4
    blob = "".join(errors)
    for token in ("人物", "规则", "陆遥"):
        assert token not in blob


@pytest.mark.asyncio
async def test_h5b_unreachable_before_token_is_busy(chat_service, scaled_idle):
    from app.services.generation_errors import PROVIDER_BUSY

    chat_service.provider = _TimedProvider(first_delay_s=0, raise_exc=ConnectionError("mlx unreachable: refused"))
    events, _ = await asyncio.wait_for(_run(chat_service), timeout=5)
    assert PROVIDER_BUSY in _errors(events)
