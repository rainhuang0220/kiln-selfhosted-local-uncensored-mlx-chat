"""V15: bind events to people; hide compiler IR from the Studio public payload."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

SOURCE = (Path(__file__).parent / "fixtures" / "preset_ten_people.txt").read_text("utf-8")
PEOPLE = {"祁律", "顾遥", "褚衡", "林夏", "阿沈", "沈知意", "方晏", "叶澄", "裴晚", "阮疏", "岑照"}
FORBIDDEN = ("待确认", "未定义", "文档分区", "needs_review", "suggested_who", "source_span")


def _public():
    from app.services.context_presets import preview_preset, public_studio_payload

    return public_studio_payload(preview_preset(SOURCE))


def test_b1_public_preview_events_all_named_from_harvest():
    public = _public()
    known = {c["name"] for c in public["characters"]}
    assert known >= PEOPLE
    assert public["timeline"]
    assert 8 <= len(public["timeline"]) <= 20
    for event in public["timeline"]:
        assert len(event["who"]) >= 1
        assert all(name in known for name in event["who"])
        assert "needs_review" not in event
        assert "suggested_who" not in event


def test_b1_stubbed_decisions_bind_orphans_or_drop():
    from app.services.context_compiler import bind_timeline_events
    from app.services.context_presets import preview_preset, public_studio_payload
    from app.services.preset_structure import extract_timeline
    from app.services.style_bank import split_style_corpus

    draft = preview_preset(SOURCE)
    # Simulate V13 orphans by clearing who on a copy of raw candidates.
    split = split_style_corpus(SOURCE)
    names = [c["name"] for c in draft["characters"]]
    raw = extract_timeline(SOURCE, split.corpus, names)
    for item in raw:
        item["who"] = []
        item["needs_review"] = True
        item["suggested_who"] = [names[0]]
    draft["timeline"] = raw
    decisions = {item["id"]: (item["suggested_who"][0] if item["suggested_who"] else "DROP") for item in raw[:3]}
    for item in raw[3:]:
        decisions[item["id"]] = "DROP"
    bound = bind_timeline_events(SOURCE, draft, decisions=decisions)
    public = public_studio_payload(bound)
    assert all(event["who"] for event in public["timeline"])
    assert all(name in {c["name"] for c in public["characters"]} for event in public["timeline"] for name in event["who"])


def test_b2_alignment_planted_people_have_own_evidence():
    public = _public()
    with_event = 0
    for name in PEOPLE:
        events = [e for e in public["timeline"] if name in e["who"]]
        if not events:
            continue
        with_event += 1
        assert any(name in (e.get("evidence") or e.get("summary") or "") for e in events)
        for event in events:
            evidence = event.get("evidence") or event.get("summary") or ""
            if name not in evidence:
                # Binder may have rewritten summary; who must still match a name in evidence.
                assert any(other in evidence for other in event["who"])
    assert with_event >= 8


def test_b3_spa_strip_omits_ir_homework_fields():
    public = _public()
    blob = json.dumps(public, ensure_ascii=False)
    assert "context_ir" not in public
    assert "segments" not in public
    for token in ("needs_review", "suggested_who", "source_span"):
        assert token not in blob
    for event in public["timeline"]:
        assert "type" not in event


def test_b4_no_homework_strings_in_public_preview():
    public = _public()
    blob = json.dumps(public, ensure_ascii=False)
    for token in FORBIDDEN:
        assert token not in blob


def test_b5_head_wins_customer_identity():
    from app.services.context_presets import preview_preset

    draft = preview_preset(SOURCE)
    assert "顾客" in draft["me"]["identity"]
    assert "妹妹" not in draft["me"]["identity"]
    public = _public()
    assert "顾客" in public["me"]["identity"]


def test_b6_default_hop_excludes_reference_evidence(chat_service, fake_provider):
    from app.services.context_presets import preview_preset, reference_context_for_mention, save_preset
    from app.services.context_compiler import route_context

    draft = preview_preset(SOURCE)
    saved = save_preset("V15 hop", draft, SOURCE, owner_id="owner-v15")
    open_hop = route_context(saved["payload"]["context_ir"], "开始聊天")
    assert open_hop.intent == "roleplay"
    assert "橙花披肩" not in open_hop.fence
    assert "顾遥那天把钥匙" not in open_hop.fence
    recalled = reference_context_for_mention(saved["payload"], "顾遥那天发生了什么？")
    assert recalled and "顾遥" in recalled
    assert "褚衡" not in recalled or "顾遥" in recalled
    # Only 顾遥 history — 祁律's unique phrase stays out.
    assert "橙花披肩" not in recalled


@pytest.mark.asyncio
async def test_b8_chat_send_skips_binder(chat_service, fake_provider):
    from app.services.context_presets import preview_preset, save_preset

    draft = preview_preset(SOURCE)
    saved = save_preset("V15 send", draft, SOURCE, owner_id="owner-v15b")
    with patch("app.services.context_compiler.binder.bind_with_model", new=AsyncMock()) as bind_mock:
        with patch("app.services.context_presets.deep_preview_preset", new=AsyncMock()) as deep_mock:
            events = [
                event
                async for event in chat_service.chat(
                    message="开始聊天",
                    conversation_id=None,
                    stream=True,
                    profile="immersive",
                    auto_continue=False,
                    max_tokens=64,
                    owner_id="owner-v15b",
                    context_preset_id=saved["id"],
                )
            ]
            assert not [event for event in events if event.get("event") == "error"]
            bind_mock.assert_not_called()
            deep_mock.assert_not_called()


def test_b7_under18_sexual_events_are_dropped_not_reviewed():
    from app.services.context_presets import preview_preset, public_studio_payload

    snippet = (
        "你是店主，我是你的顾客，我12岁，小学三年级。"
        "以下内容是幻想参考。"
        "阿青是邻居。阿青那天和我上床。"
    )
    public = public_studio_payload(preview_preset(snippet))
    blob = json.dumps(public, ensure_ascii=False)
    assert "上床" not in blob
    assert "待确认" not in blob
    assert all("上床" not in (e.get("summary") or "") for e in public["timeline"])
    assert all("上床" not in (e.get("evidence") or "") for e in public["timeline"])
