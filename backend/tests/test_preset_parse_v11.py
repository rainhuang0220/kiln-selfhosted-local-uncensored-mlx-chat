"""V11: long narrative preset paste → many real name rows, not one nickname."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.providers.base import ChatChunk, ChatRequest

FIXTURE = (Path(__file__).parent / "fixtures" / "preset_ten_people.txt").read_text(encoding="utf-8")
PLANTED = [
    "祁律",
    "顾遥",
    "褚衡",
    "林夏",
    "阿沈",
    "沈知意",
    "方晏",
    "叶澄",
    "裴晚",
    "阮疏",
]
UNIQUE_PHRASE = "橙花披肩在祁律肩上"
JUNK = ("湿透", "方先", "钥匙放")


def _name_set(draft: dict) -> set[str]:
    return {str(c.get("name") or "") for c in draft.get("characters") or []}


def test_fixture_shape_and_traps():
    assert 2000 <= len(FIXTURE) <= 4500
    assert FIXTURE.index("我是你的顾客") < 40
    assert "我是她妹妹" in FIXTURE
    assert UNIQUE_PHRASE in FIXTURE
    for name in PLANTED:
        assert name in FIXTURE
    for junk in ("湿透", "方先"):
        assert junk in FIXTURE


def test_rules_preview_harvests_ten_people_without_mlx():
    from app.services.context_presets import preview_preset

    draft = preview_preset(FIXTURE)
    names = _name_set(draft)
    hit = names & set(PLANTED)
    assert len(hit) >= 8, f"expected ≥8/10 planted names, got {sorted(hit)} from {sorted(names)}"
    for junk in JUNK:
        assert junk not in names, f"junk token leaked as character name: {junk}"
    me = draft["me"]["identity"]
    assert "顾客" in me or me == "我是你的顾客", me
    scene = draft["current_scene"]
    assert UNIQUE_PHRASE not in scene
    leaked = [n for n in PLANTED if n in scene]
    assert len(leaked) < 4, f"current_scene swallowed corpus names: {leaked}"
    assert "技师" in scene or "顾客" in scene or "风俗店" in scene


def test_live_wo_beats_corpus_trap():
    from app.services.context_presets import preview_preset

    draft = preview_preset(FIXTURE)
    identity = draft["me"]["identity"]
    assert "妹妹" not in identity
    assert "顾客" in identity


async def test_deep_json_merge_enriches_identities():
    from app.services.context_presets import merge_people_extract, preview_preset

    draft = preview_preset(FIXTURE)
    model_json = json.dumps(
        {
            "current_scene": "风俗店里技师接待顾客。",
            "me": {"identity": "顾客", "real_background": "上海做设计", "explicit_prefs": "慢节奏"},
            "characters": [
                {"name": "祁律", "identity": "大学室友", "one_event": "把帆布包扔在玄关"},
                {"name": "顾遥", "identity": "前同事", "one_event": "把钥匙放在桌上"},
                {"name": "褚衡", "identity": "顾遥的表哥", "one_event": "叫我别站在风口"},
                {"name": "林夏", "identity": "花店店员", "one_event": "说她会晚到"},
                {"name": "阿沈", "identity": "对门邻居", "one_event": "手停在门把上"},
                {"name": "沈知意", "identity": "图书馆管理员", "one_event": "叫我别紧张"},
                {"name": "方晏", "identity": "沈知意的同事", "one_event": "问过一次地址"},
                {"name": "叶澄", "identity": "画室助教", "one_event": "说风很大"},
                {"name": "裴晚", "identity": "咖啡馆店主", "one_event": "把伞往我这边倾"},
                {"name": "阮疏", "identity": "高中同桌", "one_event": "把窗帘拉上一半"},
                {"name": "湿透", "identity": "应被拒绝", "one_event": "x"},
                {"name": "虚构人", "identity": "不在原文", "one_event": "x"},
            ],
        },
        ensure_ascii=False,
    )
    merged = merge_people_extract(FIXTURE, draft, model_json)
    names = _name_set(merged)
    assert len(names & set(PLANTED)) >= 8
    assert "湿透" not in names
    assert "虚构人" not in names
    assert "顾客" in merged["me"]["identity"]
    assert UNIQUE_PHRASE not in merged["current_scene"]
    qilu = next(c for c in merged["characters"] if c["name"] == "祁律")
    assert "室友" in qilu["identity"]


@pytest.mark.asyncio
async def test_preview_api_deep_flag_calls_enrich_with_timeout(client):
    from app.services import context_presets as presets

    calls: list[float] = []

    async def fake_deep(source, draft, provider):
        calls.append(1)
        draft = dict(draft)
        draft["characters"] = [
            {"name": "祁律", "identity": "大学室友", "one_event": None},
            {"name": "顾遥", "identity": "前同事", "one_event": None},
        ]
        return draft

    with patch.object(presets, "deep_preview_preset", new=AsyncMock(side_effect=fake_deep)):
        response = client.post(
            "/context/presets/preview",
            json={"text": FIXTURE, "deep": True},
        )
    assert response.status_code == 200
    assert calls == [1]
    draft = response.json()["draft"]
    assert "characters" in draft


@pytest.mark.asyncio
async def test_preview_api_deep_timeout_keeps_rules_rows(client):
    from app.services import context_presets as presets

    async def slow_deep(source, draft, provider):
        await asyncio.sleep(30)
        return draft

    with patch.object(presets, "deep_preview_preset", new=AsyncMock(side_effect=slow_deep)):
        # Shrink wait_for so the unit test does not sit 20s.
        with patch("app.main.asyncio.wait_for", side_effect=TimeoutError):
            response = client.post(
                "/context/presets/preview",
                json={"text": FIXTURE, "deep": True},
            )
    assert response.status_code == 200
    draft = response.json()["draft"]
    assert len(draft["characters"]) >= 8
    assert "顾客" in draft["me"]["identity"]
    assert any("规则预览" in note for note in draft.get("uncertain") or [])


@pytest.mark.asyncio
async def test_chat_send_still_skips_provider_extract(chat_service, fake_provider):
    extract_calls: list[int] = []

    async def spy_deep(*_a, **_k):
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
                message=FIXTURE,
                conversation_id=None,
                stream=True,
                profile="immersive",
                auto_continue=False,
                max_tokens=64,
                owner_id="user-a",
            )
        ]
    assert extract_calls == []
    assert events


@pytest.mark.asyncio
async def test_optional_live_mlx_extract_hits_six_names():
    """Live 9B enrich — opt-in via KILN_LIVE_MLX=1; skip otherwise."""
    import os

    import httpx

    if os.environ.get("KILN_LIVE_MLX") != "1":
        pytest.skip("set KILN_LIVE_MLX=1 to run live enrich")
    try:
        models = httpx.get("http://127.0.0.1:8081/v1/models", timeout=2.0)
        models.raise_for_status()
    except Exception:
        pytest.skip("MLX not reachable")

    from app.config import Settings
    from app.providers.mlx import MlxProvider
    from app.services.context_presets import deep_preview_preset, preview_preset

    provider = MlxProvider(Settings(mlx_base_url="http://127.0.0.1:8081"))
    draft = preview_preset(FIXTURE)
    try:
        enriched = await asyncio.wait_for(deep_preview_preset(FIXTURE, draft, provider), timeout=25)
    except Exception as exc:
        pytest.skip(f"deep enrich unavailable: {exc}")
    finally:
        await provider.aclose()
    names = _name_set(enriched)
    assert len(names & set(PLANTED)) >= 6, sorted(names)
