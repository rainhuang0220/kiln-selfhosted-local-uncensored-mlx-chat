"""V10 simple account presets + stream hang contract (P1–P5)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.providers.base import ChatChunk, ChatRequest
from app.services import character_cards as cards_mod

FX = json.loads((Path(__file__).parent / "fixtures" / "style_corpus_massage.json").read_text("utf-8"))
OFFSTAGE = [item["name"] for item in FX["offstage"]]
CORPUS = "".join(FX["paragraphs"]) + FX["techniques"] + FX["register"]
OWNER_LIVE = "你是一个风俗店的技师，我是你的顾客。"
OWNER_MARKER = "以下内容是我的信息背景和性瘾参考。"
LABELED = "现实背景：我在上海工作。\n偏好：慢节奏、短句。\n"
P1_FIXTURE = f"{OWNER_LIVE}\n{OWNER_MARKER}\n{LABELED}{CORPUS}"
assert 2000 <= len(P1_FIXTURE) <= 4000
assert len(OFFSTAGE) == 10


def test_p1_parse_slots_split_characters_out_of_scene():
    from app.services.context_presets import preview_preset

    draft = preview_preset(P1_FIXTURE)
    scene = draft["current_scene"]
    assert "技师" in scene or "顾客" in scene or "风俗店" in scene
    for name in OFFSTAGE:
        assert name not in scene, f"{name} leaked into current_scene"
    characters = draft["characters"]
    assert len(characters) >= 6
    for row in characters:
        assert row.get("name")
        assert row.get("identity")
    me = draft["me"]
    assert me.get("explicit_prefs") not in (None, "", "暂无") or me.get("real_background") not in (
        None,
        "",
        "暂无",
    )
    blob = json.dumps(draft, ensure_ascii=False)
    assert "reference_people" not in draft
    assert "style_bank" not in draft
    assert "深度分析" not in blob


def test_p2_account_scope_characters_survive_new_conversation(chat_service):
    from app.services.context_presets import preview_preset, save_simple_library

    draft = preview_preset(P1_FIXTURE)
    saved = save_simple_library(
        draft,
        source_text=P1_FIXTURE,
        owner_id="user-a",
        title="风俗店",
    )
    assert saved["owner_id"] == "user-a"
    cards = cards_mod.list_cards(owner_id="user-a")
    assert len(cards) >= 6
    for card in cards:
        assert "conversation_id" not in card or card.get("conversation_id") in (None, "")
    again = cards_mod.list_cards(owner_id="user-a")
    names = {c["name"] for c in again}
    assert len(names & set(OFFSTAGE)) >= 6


def test_p3_preview_api_has_no_internals_required_by_ui(client):
    response = client.post("/context/presets/preview", json={"text": P1_FIXTURE})
    assert response.status_code == 200
    draft = response.json()["draft"]
    for forbidden in ("reference_people", "style_bank", "锚点", "深度分析"):
        assert forbidden not in draft
    assert "current_scene" in draft
    assert "me" in draft
    assert "characters" in draft
    assert "references" not in draft or draft.get("references") in (None, {})


async def test_p4_chat_send_does_not_call_llm_extract_on_3k(chat_service, fake_provider):
    extract_calls: list[Any] = []

    async def spy_deep(*_args, **_kwargs):
        extract_calls.append(1)
        raise AssertionError("LLM extract must not run on chat send")

    async def stream(request: ChatRequest):
        fake_provider.calls.append(request)
        yield ChatChunk(id="c1", model="fake", delta_content="好。")
        yield ChatChunk(
            id="c1", model="fake", finish_reason="stop", prompt_tokens=8, completion_tokens=2
        )
        yield ChatChunk(id="c1", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]
    with patch("app.services.context_presets.deep_preview_preset", new=AsyncMock(side_effect=spy_deep)):
        events = [
            ev
            async for ev in chat_service.chat(
                message=P1_FIXTURE,
                conversation_id=None,
                stream=True,
                profile="immersive",
                auto_continue=False,
                max_tokens=64,
                owner_id="user-a",
            )
        ]
    assert extract_calls == []
    assert any(e.get("event") in {"meta", "status", "delta"} for e in events)
    assert events[0]["event"] in {"status", "meta", "snapshot", "delta"}


async def test_p5_hang_contract_status_or_token_within_1s(chat_service, fake_provider):
    async def slow_stream(request: ChatRequest):
        fake_provider.calls.append(request)
        await asyncio.sleep(5)
        yield ChatChunk(id="c1", model="fake", delta_content="晚到")
        yield ChatChunk(
            id="c1", model="fake", finish_reason="stop", prompt_tokens=4, completion_tokens=2
        )
        yield ChatChunk(id="c1", model="fake", wire_done=True)

    fake_provider.stream = slow_stream  # type: ignore[method-assign]
    started = time.monotonic()
    first_event = None
    async for ev in chat_service.chat(
        message="你好",
        conversation_id=None,
        stream=True,
        profile="immersive",
        auto_continue=False,
        max_tokens=32,
        owner_id="user-a",
    ):
        first_event = ev
        break
    elapsed = time.monotonic() - started
    assert first_event is not None, "no SSE event within wait window"
    assert elapsed < 1.0, f"first event took {elapsed:.2f}s; expected status/token within 1s"
    assert first_event.get("event") in {"status", "meta", "delta", "snapshot", "ping"}
