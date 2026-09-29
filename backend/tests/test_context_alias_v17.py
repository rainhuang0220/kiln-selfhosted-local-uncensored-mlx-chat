"""V17: kinship/role aliases fold onto proper names; singleton names survive."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

DOCS = Path(__file__).resolve().parents[2] / "docs" / "test"
FIXTURES = Path(__file__).parent / "fixtures"
WOVEN = (DOCS / "多人物交织场景_输入.md").read_text("utf-8")
GOLD = json.loads((DOCS / "多人物交织场景_标准结构.json").read_text("utf-8"))
TEN = (FIXTURES / "preset_ten_people.txt").read_text("utf-8")
SHARED = (FIXTURES / "preset_shared_scene_ten.txt").read_text("utf-8")

NARRATOR = GOLD["narrator"]
GOLD_PEOPLE = [p["name"] for p in GOLD["people"] if p["name"] != NARRATOR]
ALIAS_ROWS = {"姐姐", "妈妈", "宝宝", "他", "她", "闺蜜", "队长", "校医", "妹妹", "老师"}
TEN_PEOPLE = {"祁律", "顾遥", "褚衡", "林夏", "阿沈", "沈知意", "方晏", "叶澄", "裴晚", "阮疏", "岑照"}


def _gold_resolution() -> dict:
    """Stub 9B answer derived from the gold identity field, not a second cast."""
    from app.services.context_compiler.alias import ALIAS_ROLES

    people = []
    for person in GOLD["people"]:
        if person["name"] == NARRATOR:
            continue
        head = person["identity"].split("；")[0]
        aliases = [
            token for token in sorted(ALIAS_ROLES, key=len, reverse=True)
            if len(token) >= 2 and head.endswith(token)
        ][:1]
        people.append({"name": person["name"], "aliases": aliases})
    return {"people": people, "drop": ["他", "她"]}


def _stub(payload: dict):
    calls: list = []

    async def complete(request):
        calls.append(request)
        return SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))

    complete.calls = calls
    return complete


def _public(draft):
    from app.services.context_presets import public_studio_payload

    return public_studio_payload(draft)


def _names(public) -> set[str]:
    return {row["name"] for row in public["characters"]}


# N1 ---------------------------------------------------------------------------


def test_n1_kinship_snippet_has_no_alias_rows():
    from app.services.context_presets import preview_preset

    snippet = "我是顾客。\n\n姐姐说把册子合上。妈妈让我先睡。宝宝别哭。他又看了我一眼。"
    public = _public(preview_preset(snippet))
    assert not (_names(public) & ALIAS_ROWS)
    loud = (
        "你是技师林夏。我是顾客。以下内容仅作为参考。\n\n"
        + "姐姐说把册子合上。姐姐是那种人。妈妈说让我先睡。妈妈的手很凉。"
        "宝宝说别哭。宝宝是她的小名。闺蜜说不怕。老师说慢一点。她说好。" * 6
    )
    public = _public(preview_preset(loud))
    assert not (_names(public) & ALIAS_ROWS)


def test_n1_model_fill_cannot_add_alias_rows():
    from app.services.context_presets import merge_people_extract, preview_preset

    draft = preview_preset(WOVEN)
    model = json.dumps({"characters": [
        {"name": "姐姐", "identity": "陆闻的姐姐", "evidence": "姐姐陆遥三十四岁了"},
        {"name": "闺蜜", "identity": "姐姐的闺蜜", "evidence": "她是姐姐的闺蜜"},
        {"name": "宝宝", "identity": "人物", "evidence": "宝宝"},
    ]}, ensure_ascii=False)
    merged = merge_people_extract(WOVEN, draft, model)
    assert not (_names(_public(merged)) & ALIAS_ROWS)


def test_n1_blocklist_vocabulary():
    from app.services.context_compiler.alias import is_alias_or_role

    for token in ("他", "她", "你", "我", "姐姐", "哥哥", "妹妹", "弟弟", "妈妈", "爸爸",
                  "母亲", "父亲", "宝宝", "主人", "小姐", "老师", "队长", "校医", "闺蜜",
                  "学姐", "顾客", "技师"):
        assert is_alias_or_role(token), token
    for name in ("陆遥", "沈乔", "林夏", "阿沈"):
        assert not is_alias_or_role(name), name


def test_n1_rules_fold_kinship_before_model():
    from app.services.context_compiler.alias import rules_alias_map

    assert rules_alias_map(WOVEN, ["陆遥", "沈乔"]).get("姐姐") == "陆遥"
    assert rules_alias_map("陆遥是我姐姐。后来姐姐走了。", ["陆遥"]).get("姐姐") == "陆遥"
    assert rules_alias_map("姐姐是陆遥。", ["陆遥"]).get("姐姐") == "陆遥"
    assert "老师" not in rules_alias_map("她名叫老师。", ["陆遥"])
    # Two different people claimed by one kinship word → ambiguous, no fold.
    assert "姐姐" not in rules_alias_map("姐姐陆遥来了。姐姐林见也来了。", ["陆遥", "林见"])


# N2 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_n2_gold_stub_resolves_aliases_on_woven_diary():
    from app.services.context_presets import preview_preset, resolve_preview_aliases

    stub = _stub(_gold_resolution())
    draft = await resolve_preview_aliases(WOVEN, preview_preset(WOVEN), None, complete=stub)
    assert len(stub.calls) == 1
    public = _public(draft)
    names = _names(public)
    assert set(GOLD_PEOPLE) <= names
    assert not (names & ALIAS_ROWS)
    for event in public["timeline"]:
        assert not (set(event["who"]) & ALIAS_ROWS)
    alias_only = [
        e for e in public["timeline"]
        if "陆遥" in e["who"] and "姐姐" in e["evidence"] and "陆遥" not in e["evidence"]
    ]
    assert alias_only, [(e["who"], e["evidence"][:30]) for e in public["timeline"]]
    assert "接待室" in public["current_scene"]
    assert "陆遥" not in public["current_scene"]
    assert "顾客" in public["me"]["identity"]
    assert NARRATOR not in names


@pytest.mark.asyncio
async def test_n2_resolve_prompt_is_closed_set_clips_not_whole_diary():
    from app.services.context_presets import preview_preset, resolve_preview_aliases

    stub = _stub(_gold_resolution())
    await resolve_preview_aliases(WOVEN, preview_preset(WOVEN), None, complete=stub)
    request = stub.calls[0]
    assert request.enable_thinking is False
    assert request.max_tokens <= 800
    user = request.messages[-1]["content"]
    assert "陆遥" in user and "姐姐" in user
    assert "DROP" in user
    assert len(user) < len(WOVEN)
    system = request.messages[0]["content"]
    assert "禁止把称呼本身写成人物" in system
    assert "禁止发明原文没有的人名" in system


# N3 ---------------------------------------------------------------------------


def test_n3_singleton_proper_names_survive_rules_only():
    from app.services.context_presets import preview_preset

    names = _names(_public(preview_preset(WOVEN)))
    for name in ("蒋越", "何冉", "顾青"):
        assert name in names
    assert WOVEN.count("顾青") == 1


def test_n3_singleton_anchor_does_not_need_repeat():
    from app.services.context_presets import preview_preset

    source = (
        "你是技师许澄。我是顾客。以下内容仅作为参考。\n\n"
        "那年春天在车站，周衡说他要去南方。"
        "后来在图书馆，宋黎是管理员，总替我留一张靠窗的座位。"
        "再后来，楚遥，二十七岁，把一封信交给我就走了。"
    )
    names = _names(_public(preview_preset(source)))
    for name in ("周衡", "宋黎", "楚遥"):
        assert source.count(name) == 1
        assert name in names, names


# N4 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_n4_invented_or_alias_names_from_model_are_dropped():
    from app.services.context_presets import preview_preset, resolve_preview_aliases

    stub = _stub({
        "people": [
            {"name": "赵敏", "aliases": ["姐姐"], "evidence": "赵敏是姐姐"},
            {"name": "姐姐", "aliases": [], "evidence": "姐姐陆遥三十四岁了"},
            {"name": "陆遥", "aliases": ["姐姐"]},
        ],
        "drop": [],
    })
    draft = await resolve_preview_aliases(WOVEN, preview_preset(WOVEN), None, complete=stub)
    names = _names(_public(draft))
    assert "赵敏" not in names
    assert "姐姐" not in names
    assert "陆遥" in names


@pytest.mark.asyncio
async def test_n4_resolver_identity_must_be_grounded():
    from app.services.context_presets import preview_preset, resolve_preview_aliases

    stub = _stub({
        "people": [
            {"name": "唐宁", "aliases": ["队长"], "identity": "排球队长"},
            {"name": "蒋越", "aliases": [], "identity": "负责收球"},
            {"name": "周岚", "aliases": [], "identity": "星际舰长"},
        ],
        "drop": [],
    })
    draft = await resolve_preview_aliases(WOVEN, preview_preset(WOVEN), None, complete=stub)
    identity = {row["name"]: row["identity"] for row in _public(draft)["characters"]}
    assert identity["蒋越"] == "负责收球"
    assert identity["周岚"] != "星际舰长"


# N5 / N6 ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_n5_ten_people_regression_with_resolver():
    from app.services.context_presets import preview_preset, resolve_preview_aliases

    draft = preview_preset(TEN)
    stub = _stub({"people": [{"name": n, "aliases": []} for n in TEN_PEOPLE], "drop": []})
    draft = await resolve_preview_aliases(TEN, draft, None, complete=stub)
    public = _public(draft)
    names = _names(public)
    assert names >= TEN_PEOPLE
    assert "姐姐" not in names
    assert "顾客" in public["me"]["identity"]
    assert "妹妹" not in public["me"]["identity"]


def test_n6_shared_scene_multi_who_and_default_hop_fence():
    from app.services.context_compiler import route_context
    from app.services.context_presets import preview_preset

    draft = preview_preset(SHARED)
    public = _public(draft)
    assert any({"顾遥", "褚衡", "林夏"} <= set(e["who"]) for e in public["timeline"])
    hop = route_context(draft["context_ir"], "你好")
    assert "顾遥" not in hop.fence


# N7 ---------------------------------------------------------------------------


def test_n7_preview_endpoint_calls_resolver_for_long_paste_only(client):
    # V18: the long-paste model pass is the Stage A extract, not the clip resolver.
    from app.services import context_presets as presets

    async def rules_only(source, provider, **_kw):
        return presets.model_not_ran_preview(source, "model_failed", "stub")

    with patch.object(presets, "extract_preview_preset", new=AsyncMock(side_effect=rules_only)) as resolve:
        long = client.post("/context/presets/preview", json={"text": WOVEN, "deep": True})
        assert long.status_code == 200
        assert resolve.await_count == 1
        short = client.post(
            "/context/presets/preview",
            json={"text": "你是技师许澄。我是顾客。姐姐陆遥说过一句话。", "deep": True},
        )
        assert short.status_code == 200
        assert resolve.await_count == 1


@pytest.mark.asyncio
async def test_n7_chat_send_never_calls_resolver(chat_service, fake_provider):
    from app.services import context_presets as presets

    with patch.object(presets, "resolve_preview_aliases", new=AsyncMock()) as resolve:
        events = [
            event
            async for event in chat_service.chat(
                message=WOVEN,
                conversation_id=None,
                stream=True,
                profile="immersive",
                auto_continue=False,
                max_tokens=64,
                owner_id="owner-v17",
            )
        ]
    assert not [event for event in events if event.get("event") == "error"]
    resolve.assert_not_called()


# N8 ---------------------------------------------------------------------------


def test_n8_resolver_timeout_shows_no_rules_roster(client):
    from app.services import context_presets as presets

    async def slow(*_a, **_kw):
        raise TimeoutError

    async def noisy_deep(source, draft, provider):
        out = dict(draft)
        out["characters"] = [*draft["characters"], {"name": "姐姐", "identity": "人物", "one_event": None}]
        return out

    with patch.object(presets, "resolve_preview_aliases", new=AsyncMock(side_effect=slow)):
        with patch.object(presets, "deep_preview_preset", new=AsyncMock(side_effect=noisy_deep)):
            response = client.post("/context/presets/preview", json={"text": WOVEN, "deep": True})
    assert response.status_code == 200
    draft = response.json()["draft"]
    # V19: the 9B did not analyze (FakeProvider echoes prose) → empty cards, never a rules roster.
    assert draft["characters"] == []
    assert draft["extract"]["model_ran"] is False
    blob = json.dumps(draft, ensure_ascii=False)
    for token in ("needs_review", "suggested_who", "source_span", "segments"):
        assert token not in blob
    # The diary quotes 「待确认」 on a form; it must never surface as a status.
    assert all(row["identity"] != "待确认" for row in draft["characters"])
    assert not any("待确认" in note for note in draft.get("uncertain") or [])


# N9 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_n9_under18_sexual_beats_still_dropped_by_the_binder():
    from app.services.context_presets import preview_preset, resolve_preview_aliases

    snippet = (
        "你是店主，我是你的顾客，我12岁，小学三年级。"
        "以下内容是幻想参考。"
        + "阿青是邻居。阿青那天和我上床。姐姐陆遥说过一句话。" * 34
    )
    assert len(snippet) >= 800
    stub = _stub({"people": [], "drop": []})
    draft = await resolve_preview_aliases(snippet, preview_preset(snippet), None, complete=stub)
    blob = json.dumps(_public(draft), ensure_ascii=False)
    assert "上床" not in blob
    assert "待确认" not in blob


@pytest.mark.asyncio
async def test_n9_adult_ages_still_reach_resolver():
    from app.services.context_presets import preview_preset, resolve_preview_aliases

    source = WOVEN.replace("我是二十九岁的顾客陆闻", "我是29岁的顾客陆闻", 1)
    stub = _stub(_gold_resolution())
    await resolve_preview_aliases(source, preview_preset(source), None, complete=stub)
    assert len(stub.calls) == 1


# N10 (optional live) -----------------------------------------------------------


@pytest.mark.skipif(os.environ.get("KILN_LIVE_N10") != "1", reason="live MLX resolve is opt-in")
@pytest.mark.asyncio
async def test_n10_live_resolve_woven_diary():
    import time

    from app.config import settings
    from app.providers.mlx import MlxProvider
    from app.services.context_presets import preview_preset, resolve_preview_aliases

    provider = MlxProvider(settings)
    started = time.monotonic()
    draft = await resolve_preview_aliases(WOVEN, preview_preset(WOVEN), provider, timeout_s=60.0)
    elapsed = time.monotonic() - started
    names = _names(_public(draft))
    print(f"N10 elapsed={elapsed:.1f}s names={sorted(names)}")
    assert elapsed <= 60
    assert len(names & set(GOLD_PEOPLE)) >= 10
    assert not (names & ALIAS_ROWS)
