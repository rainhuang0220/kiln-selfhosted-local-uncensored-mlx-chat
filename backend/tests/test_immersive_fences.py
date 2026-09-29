"""User-side fence packing and pin-repair continuation (immersive v0.7)."""

from __future__ import annotations

from app.providers.base import ChatChunk, ChatRequest
from app.services.fact_extractor import extract_atoms, must_keep_fence, pack_user_side_fences


def test_pack_keeps_5000_char_current_user():
    user = "测" * 5000
    keep = must_keep_fence(["物件：铜钥匙", "约定：周五"])
    lore = "<lore>\n" + ("旧设定。" * 200) + "\n</lore>"
    scene = (
        "<scene_state>\nlocation: 旧书店\ninventory: [铜钥匙]\nclock: 周五约定\n</scene_state>"
    )
    fence = pack_user_side_fences(
        must_keep=keep, lore=lore, scene_state=scene, budget_chars=600
    )
    assert fence is not None
    # Simulate chat insert: fence is a sibling user message; current user stays intact.
    messages = [
        {"role": "system", "content": "frozen"},
        {"role": "user", "content": fence, "id": "context-fences"},
        {"role": "user", "content": user},
    ]
    assert messages[0]["role"] == "system"
    assert "<must_keep>" not in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "<must_keep>" in messages[1]["content"]
    assert messages[2]["content"] == user
    assert len(messages[2]["content"]) == 5000


async def test_chat_sends_full_5000_char_user_turn(chat_service, fake_provider):
    captured: list[list[dict]] = []

    async def stream(request: ChatRequest):
        captured.append(list(request.messages))
        yield ChatChunk(id="c1", model="fake", delta_content="好。")
        yield ChatChunk(id="c1", model="fake", finish_reason="stop")
        yield ChatChunk(id="c1", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]
    user = "测" * 5000
    events = [
        ev
        async for ev in chat_service.chat(
            message=user,
            conversation_id=None,
            stream=True,
            profile="immersive",
            auto_continue=False,
            max_tokens=64,
        )
    ]
    assert not [e for e in events if e.get("event") == "error"], events[-2:]
    last_user = [m for m in captured[0] if m.get("role") == "user"][-1]
    assert last_user["content"] == user


async def test_fence_atoms_enter_user_side_not_system(chat_service, fake_provider):
    captured: list[list[dict]] = []

    async def stream(request: ChatRequest):
        captured.append(list(request.messages))
        yield ChatChunk(id="c1", model="fake", delta_content="好。")
        yield ChatChunk(
            id="c1",
            model="fake",
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=2,
        )
        yield ChatChunk(id="c1", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]

    events = []
    text = "旧书店。铜钥匙。周五。红痣。公子。"
    async for ev in chat_service.chat(
        message=text,
        conversation_id=None,
        stream=True,
        profile="immersive",
        auto_continue=False,
        max_tokens=64,
    ):
        events.append(ev)

    assert captured, events[-3:]
    messages = captured[0]
    system_blobs = [m.get("content") or "" for m in messages if m.get("role") == "system"]
    user_blobs = [m.get("content") or "" for m in messages if m.get("role") == "user"]
    joined_user = "\n".join(user_blobs)
    for pin in ("铜钥匙", "周五", "红痣", "公子", "旧书店"):
        assert pin in joined_user, pin
    for blob in system_blobs:
        assert "<must_keep>" not in blob
        assert "<lore>" not in blob
        assert "<scene_state>" not in blob
    assert any("<must_keep>" in u for u in user_blobs)
    assert text in joined_user
    fences = [m for m in messages if m.get("id") == "context-fences"]
    assert len(fences) == 1 and fences[0]["role"] == "user"
    assert "<author_note>" in fences[0]["content"]
    assert all("<author_note>" not in b for b in system_blobs)


PIN_TURN = "地点：旧书店。物件：铜钥匙。约定：周五。称呼：公子。标记：红痣。"
PINS_IN_PROSE = "旧书店里，公子把铜钥匙放回柜台，左耳后那颗红痣一闪，说好周五当面还。"
NO_PINS = "他只是点了点头，什么也没说。"


def _scripted_stream(bodies: list[str], calls: list[ChatRequest]):
    async def stream(request: ChatRequest):
        calls.append(request)
        body = bodies[min(len(calls), len(bodies)) - 1]
        yield ChatChunk(id="c1", model="fake", delta_content=body)
        yield ChatChunk(
            id="c1", model="fake", finish_reason="stop", prompt_tokens=10, completion_tokens=20
        )
        yield ChatChunk(id="c1", model="fake", wire_done=True)

    return stream


async def _run(chat_service, *, profile: str, message: str = PIN_TURN) -> list[dict]:
    return [
        ev
        async for ev in chat_service.chat(
            message=message,
            conversation_id=None,
            stream=True,
            profile=profile,
            auto_continue=False,
            max_tokens=256,
        )
    ]


async def test_pin_repair_skipped_when_pins_already_in_prose(
    chat_service, fake_provider, monkeypatch
):
    calls: list[ChatRequest] = []
    fake_provider.stream = _scripted_stream([PINS_IN_PROSE], calls)  # type: ignore[method-assign]
    monkeypatch.setattr(
        chat_service.tokenizer,
        "continuation_completion_prompt",
        lambda messages, **kwargs: ("CONTINUE_PROMPT", ""),
    )

    events = await _run(chat_service, profile="immersive")

    done = next(e for e in events if e.get("event") == "done")["data"]
    assert len(calls) == 1
    assert done["pin_repair_count"] == 0
    assert done["message"]["content"] == PINS_IN_PROSE


async def test_pin_repair_is_capped_at_one_hop(chat_service, fake_provider, monkeypatch):
    calls: list[ChatRequest] = []
    fake_provider.stream = _scripted_stream([NO_PINS, "她又低下头去。"], calls)  # type: ignore[method-assign]
    monkeypatch.setattr(
        chat_service.tokenizer,
        "continuation_completion_prompt",
        lambda messages, **kwargs: ("CONTINUE_PROMPT", ""),
    )

    events = await _run(chat_service, profile="immersive")

    done = next(e for e in events if e.get("event") == "done")["data"]
    assert len(calls) == 2
    assert done["pin_repair_count"] == 1
    assert calls[1].max_tokens <= 512
    assert done["message"]["content"] == NO_PINS + "她又低下头去。"


async def test_interactive_profiles_get_no_immersive_fences_or_repair(
    chat_service, fake_provider, monkeypatch
):
    for profile in ("interactive_dialogue", "balanced", "reasoning"):
        calls: list[ChatRequest] = []
        fake_provider.stream = _scripted_stream([NO_PINS], calls)  # type: ignore[method-assign]

        events = await _run(chat_service, profile=profile)

        assert not [e for e in events if e.get("event") == "error"], (profile, events[-2:])
        done = next(e for e in events if e.get("event") == "done")["data"]
        assert len(calls) == 1, profile
        assert done["pin_repair_count"] == 0, profile
        sent = "\n".join(m.get("content") or "" for m in calls[0].messages)
        for tag in ("<must_keep>", "<lore>", "<scene_state>", "<author_note>"):
            assert tag not in sent, (profile, tag)
        user_turns = [m for m in calls[0].messages if m.get("role") == "user"]
        assert user_turns[-1]["content"] == PIN_TURN, profile


async def test_pin_repair_triggers_when_prose_misses_pins(
    chat_service, fake_provider, monkeypatch
):
    calls = {"n": 0}
    prompts: list[ChatRequest] = []

    async def stream(request: ChatRequest):
        calls["n"] += 1
        prompts.append(request)
        if calls["n"] == 1:
            # Deliberately omit every pin noun.
            yield ChatChunk(id="c1", model="fake", delta_content="他只是点了点头，什么也没说。")
            yield ChatChunk(
                id="c1",
                model="fake",
                finish_reason="stop",
                prompt_tokens=10,
                completion_tokens=20,
            )
            yield ChatChunk(id="c1", model="fake", wire_done=True)
        else:
            yield ChatChunk(
                id="c1",
                model="fake",
                delta_content="铜钥匙还在，周五见，公子看见左耳后红痣。",
            )
            yield ChatChunk(
                id="c1",
                model="fake",
                finish_reason="stop",
                prompt_tokens=10,
                completion_tokens=30,
            )
            yield ChatChunk(id="c1", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]
    monkeypatch.setattr(
        chat_service.tokenizer,
        "continuation_completion_prompt",
        lambda messages, **kwargs: ("CONTINUE_PROMPT", "尾"),
    )

    events = []
    async for ev in chat_service.chat(
        message="地点：旧书店。物件：铜钥匙。约定：周五。称呼：公子。标记：红痣。",
        conversation_id=None,
        stream=True,
        profile="immersive",
        auto_continue=False,
        max_tokens=256,
    ):
        events.append(ev)

    dones = [e for e in events if e.get("event") == "done"]
    assert len(dones) == 1
    assert calls["n"] == 2, "pin_repair must run exactly once"
    msg = dones[0]["data"]["message"]
    assert "铜钥匙" in (msg["content"] or "")
    assert dones[0]["data"].get("pin_repair_count", 0) == 1
    metas = [e["data"] for e in events if e.get("event") == "meta"]
    assert len({m["message_id"] for m in metas}) == 1, "repair must reuse the same message_id"
    assert msg["id"] == metas[0]["message_id"]
    assert msg["content"].startswith("他只是点了点头")
    conv = chat_service.get_conversation(metas[0]["conversation_id"])
    assistants = [m for m in conv["messages"] if m["role"] == "assistant"]
    assert [m["id"] for m in assistants] == [msg["id"]], "repair must not add a second bubble"
    assert assistants[0]["content"] == msg["content"]
    # Second call must be a continuation on same assistant path (raw prompt or messages).
    assert prompts[0].max_tokens != 512 or prompts[1].max_tokens <= 512
    assert prompts[1].max_tokens <= 512


def test_extract_atoms_smoke_for_seed_fixture():
    atoms = extract_atoms("旧书店 + 铜钥匙 + 周五 + 红痣 + 公子")
    fence = must_keep_fence(atoms)
    assert fence and "铜钥匙" in fence and "公子" in fence
