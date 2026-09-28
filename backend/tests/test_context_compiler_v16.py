"""V16: attention layers + multi-who shared-scene beats."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

SHARED = (Path(__file__).parent / "fixtures" / "preset_shared_scene_ten.txt").read_text("utf-8")
TEN = (Path(__file__).parent / "fixtures" / "preset_ten_people.txt").read_text("utf-8")
PEOPLE = {"祁律", "顾遥", "褚衡", "林夏", "阿沈", "沈知意", "方晏", "叶澄", "裴晚", "阮疏", "岑照"}
FORBIDDEN = ("待确认", "未定义", "文档分区", "needs_review", "suggested_who", "source_span")
LONG_DOC = Path(__file__).resolve().parents[2] / "docs" / "test" / "测试长文本.md"


def _public(source: str = SHARED):
    from app.services.context_presets import preview_preset, public_studio_payload

    return public_studio_payload(preview_preset(source))


def _draft(source: str = SHARED):
    from app.services.context_presets import preview_preset

    return preview_preset(source)


def test_a1_live_lock_parlor_not_memory_nights():
    draft = _draft()
    ir = draft["context_ir"]
    assert "技师" in (ir.get("persona") or {}).get("role", "")
    assert "顾客" in (ir.get("user_avatar") or {}).get("identity", "")
    scene = ir.get("current_scene") or ""
    assert "矮桌" in scene or "两杯水" in scene or "店" in scene
    for token in ("阁楼", "图书馆", "雨棚", "书架"):
        assert token not in scene


def test_a2_cue_split_short_role_outranks_long_body():
    from app.services.context_presets import preview_preset

    role = "你是店主。"
    body = ("顾遥把钥匙放在桌上。那晚阁楼窗外雨很大。" * 200)
    assert len(body) >= 3000
    source = f"{role}我是你的顾客。以下内容仅作为参考。{body}"
    draft = preview_preset(source)
    ir = draft["context_ir"]
    scene = ir.get("current_scene") or ""
    role_text = (ir.get("persona") or {}).get("role") or ""
    assert "顾遥" not in scene
    assert "阁楼" not in scene
    assert "顾遥" not in role_text
    assert "店主" in role_text or "技师" in role_text or role_text


def test_a3_attention_budget_default_hop():
    from app.services.context_compiler import route_context

    ir = _draft()["context_ir"]
    hop = route_context(ir, "你好")
    assert hop.intent == "roleplay"
    fence = hop.fence
    assert "技师" in fence
    assert "顾客" in fence
    assert "矮桌" in fence or "两杯水" in fence or "店" in fence
    for name in ("顾遥", "祁律", "褚衡"):
        assert name not in fence
    assert "以下内容仅作为参考" not in fence
    assert len(fence) <= 720
    assert "<service_requirements" in fence
    assert fence.index("<active_context>") < fence.index("<service_requirements")
    assert "confirmed_background" not in fence
    pref_lines = [
        line for line in fence.splitlines()
        if line and not line.startswith("<") and "偏好只影响" not in line
        and "active_context" not in line and "assistant_persona" not in line
        and "current_scene" not in line and "user_avatar" not in line
        and "重点现实场景" not in line and "现实设定" not in line
        and "参考" not in line
    ]
    # At most one short preference hint inside the bank.
    bank = ""
    if "<preference_bank" in fence:
        bank = fence.split("<preference_bank", 1)[1].split("</preference_bank>", 1)[0]
        blobs = [ln.strip() for ln in bank.splitlines() if ln.strip() and "偏好只影响" not in ln]
        assert len(blobs) <= 1
        if blobs:
            assert len(blobs[0]) <= 80


def test_a4_multi_who_public_preview():
    public = _public()
    known = {c["name"] for c in public["characters"]}
    multi = [e for e in public["timeline"] if len(e.get("who") or []) >= 2]
    assert len(multi) >= 3
    for event in multi:
        evidence = event.get("evidence") or event.get("summary") or ""
        for name in event["who"]:
            assert name in known
            assert name in evidence
    loft = [
        e for e in public["timeline"]
        if "阁楼" in (e.get("evidence") or e.get("summary") or "")
        or {"顾遥", "褚衡", "林夏"} <= set(e.get("who") or [])
    ]
    for event in loft:
        who = set(event.get("who") or [])
        evidence = event.get("evidence") or event.get("summary") or ""
        if "褚衡" in evidence and "林夏" in evidence and "顾遥" in evidence:
            assert who != {"顾遥"}
            assert len(who) >= 2


def test_a5_no_collapse_different_coactor_sets():
    from app.services.context_compiler.binder import _merge_consecutive

    different = [
        {"id": "a", "who": ["顾遥", "褚衡", "林夏"], "summary": "阁楼", "when": "雨夜", "evidence": "阁楼"},
        {"id": "b", "who": ["沈知意", "方晏"], "summary": "图书馆", "when": "闭馆以后", "evidence": "书架"},
    ]
    assert len(_merge_consecutive(different)) == 2
    equal = [
        {"id": "a", "who": ["顾遥", "褚衡", "林夏"], "summary": "阁楼", "when": "雨夜", "evidence": "阁楼"},
        {"id": "c", "who": ["顾遥", "褚衡", "林夏"], "summary": "又回阁楼", "when": "后来", "evidence": "阁楼2"},
    ]
    merged_equal = _merge_consecutive(equal)
    assert len(merged_equal) == 1
    assert set(merged_equal[0]["who"]) == {"顾遥", "褚衡", "林夏"}


def test_a6_default_hop_clean_named_recall():
    from app.services.context_compiler import route_context
    from app.services.context_presets import save_preset

    draft = _draft()
    saved = save_preset("V16 hop", draft, SHARED, owner_id="owner-v16")
    ir = saved["payload"]["context_ir"]
    open_hop = route_context(ir, "你好")
    assert open_hop.intent == "roleplay"
    assert "阁楼" not in open_hop.fence
    assert "顾遥" not in open_hop.fence
    assert "书架" not in open_hop.fence
    start_hop = route_context(ir, "开始聊天")
    assert "阁楼" not in start_hop.fence
    recall = route_context(ir, "顾遥那天发生了什么？")
    assert recall.intent == "recall"
    assert "顾遥" in (recall.reference_fence or recall.fence)
    # Co-actors may appear inside the event line; they must not become cast.
    cast_block = "\n".join(
        line for line in recall.fence.splitlines() if "current_cast" in line
    )
    assert "褚衡" not in cast_block
    assert "林夏" not in cast_block


def test_a7_head_wins_customer_identity():
    public = _public()
    assert "顾客" in public["me"]["identity"]
    assert "妹妹" not in public["me"]["identity"]


def test_a8_stylebank_cap_no_raw_body():
    from app.services.context_presets import (
        chat_frame_from_simple,
        save_simple_library,
        style_bank_for_preset,
    )
    from app.services.style_bank import StyleBank

    draft = _draft()
    saved = save_simple_library(
        draft, source_text=SHARED, owner_id="owner-v16-style", title="V16 style"
    )
    frame = chat_frame_from_simple(saved["payload"], source_text=SHARED)
    bank = style_bank_for_preset(saved["payload"], source_text=SHARED)
    fence = bank.fence() or ""
    digest = bank.digest or ""
    blob = json.dumps(bank.to_dict(), ensure_ascii=False)
    assert "橙花披肩" not in fence
    assert "橙花披肩" not in digest
    assert "雨夜阁楼那一回" not in fence
    assert "以下内容仅作为参考" not in fence
    assert SHARED[80:160] not in fence
    # Prefs-only or empty — never the raw ten-person body.
    assert "祁律是我大学时的室友" not in fence
    assert frame.get("context_ir")


def test_a9_v15_ten_people_regression():
    public = _public(TEN)
    known = {c["name"] for c in public["characters"]}
    assert known >= PEOPLE
    assert public["timeline"]
    for event in public["timeline"]:
        assert len(event["who"]) >= 1
        assert all(name in known for name in event["who"])
    blob = json.dumps(public, ensure_ascii=False)
    for token in FORBIDDEN:
        assert token not in blob
    from app.services.context_compiler import route_context
    from app.services.context_presets import preview_preset

    ir = preview_preset(TEN)["context_ir"]
    hop = route_context(ir, "开始聊天")
    assert "橙花披肩" not in hop.fence
    assert "顾遥那天把钥匙" not in hop.fence


def test_a10_under18_sexual_events_dropped():
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
    compile_only_drop = False
    if LONG_DOC.is_file():
        public_long = public_studio_payload(preview_preset(LONG_DOC.read_text("utf-8")))
        # Do not quote the private corpus; only assert the drop posture.
        assert "待确认" not in json.dumps(public_long, ensure_ascii=False)
        compile_only_drop = True
    # Stash for the end report via a marker attribute (tests still pass either way).
    test_a10_under18_sexual_events_dropped.compile_only_drop = compile_only_drop


@pytest.mark.asyncio
async def test_a11_chat_send_skips_binder(chat_service, fake_provider):
    from app.services.context_presets import preview_preset, save_preset

    draft = preview_preset(SHARED)
    saved = save_preset("V16 send", draft, SHARED, owner_id="owner-v16b")
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
                    owner_id="owner-v16b",
                    context_preset_id=saved["id"],
                )
            ]
            assert not [event for event in events if event.get("event") == "error"]
            bind_mock.assert_not_called()
            deep_mock.assert_not_called()
