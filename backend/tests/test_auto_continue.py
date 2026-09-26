"""Auto-continue toward min_output_chars on the same assistant message_id."""

from __future__ import annotations

from app.providers.base import ChatChunk, ChatRequest
from app.services.auto_continue import count_output_chars, should_auto_continue


def test_should_auto_continue_on_length_under_min():
    assert should_auto_continue(
        visible_chars=1800,
        finish_reason="length",
        min_output_chars=5000,
        auto_continue_count=0,
        auto_continue_max=3,
    )
    assert not should_auto_continue(
        visible_chars=5200,
        finish_reason="length",
        min_output_chars=5000,
        auto_continue_count=0,
        auto_continue_max=3,
    )


def test_should_auto_continue_on_stop_under_min():
    assert should_auto_continue(
        visible_chars=3200,
        finish_reason="stop",
        min_output_chars=5000,
        auto_continue_count=0,
        auto_continue_max=3,
        user_text="好。",
    )
    assert should_auto_continue(
        visible_chars=1000,
        finish_reason="completed_length",
        min_output_chars=5000,
        auto_continue_count=0,
        auto_continue_max=3,
    )
    assert not should_auto_continue(
        visible_chars=3200,
        finish_reason="stop",
        min_output_chars=5000,
        auto_continue_count=3,
        auto_continue_max=3,
    )


def test_count_output_chars_ignores_whitespace():
    assert count_output_chars("你 好\n世界") == 4


def _varied(n: int, tag: str) -> str:
    # Avoid hard_self_loop on identical glyph runs.
    parts = []
    while count_output_chars("".join(parts)) < n:
        i = len(parts)
        parts.append(f"{tag}{i}动作与呼吸变化，场景向前推进。")
    return "".join(parts)


async def test_chat_auto_continue_same_message_id(chat_service, fake_provider, monkeypatch):
    short = _varied(1800, "甲")
    more = _varied(3500, "乙")
    calls = {"n": 0}

    monkeypatch.setattr(
        chat_service.tokenizer,
        "continuation_completion_prompt",
        lambda messages, **kwargs: ("CONTINUE_PROMPT", "尾"),
    )

    async def stream(request: ChatRequest):
        calls["n"] += 1
        if calls["n"] == 1:
            yield ChatChunk(id="c1", model="fake", delta_content=short)
            yield ChatChunk(
                id="c1",
                model="fake",
                finish_reason="length",
                prompt_tokens=10,
                completion_tokens=100,
            )
            yield ChatChunk(id="c1", model="fake", wire_done=True)
        else:
            yield ChatChunk(id="c1", model="fake", delta_content=more)
            yield ChatChunk(
                id="c1",
                model="fake",
                finish_reason="stop",
                prompt_tokens=10,
                completion_tokens=200,
            )
            yield ChatChunk(id="c1", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]

    events = []
    async for ev in chat_service.chat(
        message="继续",
        conversation_id=None,
        stream=True,
        profile="immersive",
        auto_continue=True,
        max_tokens=6144,
    ):
        events.append(ev)

    dones = [e for e in events if e.get("event") == "done"]
    assert len(dones) == 1, events[-3:]
    msg = dones[0]["data"]["message"]
    visible = count_output_chars(msg["content"])
    assert visible >= 5000, (visible, dones[0]["data"].get("finish_reason"), calls["n"])
    assert calls["n"] >= 2
    assert msg["id"]
    assert dones[0]["data"].get("visible_chars", visible) >= 5000
