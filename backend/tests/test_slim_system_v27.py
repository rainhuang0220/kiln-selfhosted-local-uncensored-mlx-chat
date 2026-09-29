"""V27: keep the last user line visible beside a short live-scene pin."""

from pathlib import Path

from app.services.context_compiler import route_context
from app.services.context_presets import chat_frame_from_simple, preview_preset
from app.services.literary_system import compile_system
from app.services.profiles import resolve_profile
import pytest


FIXTURE = Path(__file__).parent / "fixtures" / "overnight_wenai_parlor.txt"
V23_SYSTEM_CHARS = 567
V23_DEFAULT_FENCE_CHARS = 693
V23_AUTHOR_NOTE_CHARS = 198


def _frame():
    source = FIXTURE.read_text("utf-8")
    return chat_frame_from_simple(preview_preset(source), source_text=source)


def test_compiled_grounded_system_is_one_short_block():
    frame = _frame()
    card = {**frame.get("active_character", {}), "scenario": frame.get("active_scene") or ""}
    system = compile_system(card, grounded_context=True)
    assert system.startswith("写成人向文爱小说。")
    assert "先接上一句用户输入" in system
    for excess in ("角色演员", "至少 1500", "10000 字", "接触面、呼吸、力道", "<character>"):
        assert excess not in system
    assert len(system) < V23_SYSTEM_CHARS


def test_bare_hello_ends_in_short_live_scene_without_rule_banks():
    fence = route_context(_frame()["context_ir"], "你好").fence
    assert fence.splitlines()[-1].startswith("此刻现场：")
    assert "技师" in fence and "顾客" in fence and "接待室" in fence
    assert len(fence.splitlines()[-1].removeprefix("此刻现场：")) <= 160
    for excess in ("<service_requirements>", "<service_requirements ", "<style_digest", "do_not_literalize", "陆遥", "<active_context>"):
        assert excess not in fence
    assert len(fence) < V23_DEFAULT_FENCE_CHARS


def test_default_prompt_is_shorter_than_v23_production():
    frame = _frame()
    card = {**frame.get("active_character", {}), "scenario": frame.get("active_scene") or ""}
    system = compile_system(card, grounded_context=True)
    fence = route_context(frame["context_ir"], "你好").fence
    old = V23_SYSTEM_CHARS + V23_DEFAULT_FENCE_CHARS + V23_AUTHOR_NOTE_CHARS + len("你好")
    new = len(system) + len(fence) + len("你好")
    print(f"V23={old} chars; V27={new} chars; system={len(system)}; fence={len(fence)}")
    assert new < old // 2


def test_named_person_still_recalls_only_that_person_events():
    ir = _frame()["context_ir"]
    ir["entities"] = [{"name": "陆遥", "identity": "姐姐"}, {"name": "沈乔", "identity": "朋友"}]
    ir["events"] = [
        {"order": 1, "actors": ["陆遥"], "description": "陆遥在书店归还了钥匙"},
        {"order": 2, "actors": ["沈乔"], "description": "沈乔在球场等候"},
    ]
    assert "陆遥" not in route_context(ir, "你好").fence
    recall = route_context(ir, "陆遥是谁")
    assert recall.intent == "recall"
    assert "陆遥在书店归还了钥匙" in recall.fence
    assert "沈乔在球场等候" not in recall.fence


def test_immersive_first_hop_has_no_five_thousand_character_floor():
    profile = resolve_profile("immersive")
    assert profile["max_tokens"] == 6144
    assert profile["min_output_chars"] <= 800


@pytest.mark.asyncio
async def test_bound_chat_places_live_scene_at_end_of_context_fence(chat_service, fake_provider):
    from app.services.context_presets import save_preset

    source = FIXTURE.read_text("utf-8")
    saved = save_preset("V27 slim", preview_preset(source), source, owner_id="owner-v27")
    events = [event async for event in chat_service.chat(
        message="你好", conversation_id=None, stream=True, profile="immersive",
        auto_continue=True, max_tokens=32, owner_id="owner-v27", context_preset_id=saved["id"],
    )]
    assert not [event for event in events if event.get("event") == "error"]
    assert len(fake_provider.calls) == 1
    cid = next(event for event in events if event.get("event") == "meta")["data"]["conversation_id"]
    for message_text in ("你好", "你靠近一点"):
        if message_text != "你好":
            followup = [event async for event in chat_service.chat(
                message=message_text, conversation_id=cid, stream=True, profile="immersive",
                auto_continue=True, max_tokens=32, owner_id="owner-v27",
            )]
            assert not [event for event in followup if event.get("event") == "error"]
            assert len(fake_provider.calls) == 2
        sent = fake_provider.calls[-1].messages
        assert sent[0]["role"] == "system" and "<character>" not in sent[0]["content"]
        context = next(message["content"] for message in sent if message.get("id") == "context-fences")
        assert context.splitlines()[-1].startswith("此刻现场：")
        assert "<author_note>" not in context
        assert sent[-1]["content"] == message_text
