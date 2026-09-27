"""Auto-continue toward min_output_chars on the same assistant message_id."""

from __future__ import annotations

import pytest

from app.providers.base import ChatChunk, ChatRequest
from app.services.auto_continue import count_output_chars, drop_last_sentence, should_auto_continue


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


def test_should_auto_continue_respects_completion_soft_cap():
    assert should_auto_continue(
        visible_chars=1000,
        finish_reason="length",
        min_output_chars=5000,
        auto_continue_count=0,
        auto_continue_max=3,
        completion_tokens_used=6000,
        completion_soft_cap=12288,
    )
    assert not should_auto_continue(
        visible_chars=1000,
        finish_reason="length",
        min_output_chars=5000,
        auto_continue_count=0,
        auto_continue_max=3,
        completion_tokens_used=12288,
        completion_soft_cap=12288,
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


@pytest.mark.parametrize("first_finish", ["length", "stop"])
async def test_chat_auto_continue_same_message_id(
    chat_service, fake_provider, monkeypatch, first_finish
):
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
                finish_reason=first_finish,
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
    metas = [e["data"] for e in events if e.get("event") == "meta"]
    assert {m["message_id"] for m in metas} == {msg["id"]}
    # A self-stopped hop resumes before its closed last sentence (next beat, not a rewrite).
    kept = short if first_finish == "length" else drop_last_sentence(short)
    assert msg["content"].startswith(kept)
    assert dones[0]["data"].get("visible_chars", visible) >= 5000


async def test_fill_hop_bans_eos_and_drops_reprinted_previous_reply(
    chat_service, fake_provider, monkeypatch
):
    prev_reply = _varied(600, "旧")
    fresh = _varied(1500, "新")
    fill = _varied(4200, "续")
    requests: list[ChatRequest] = []
    calls = {"n": 0}

    monkeypatch.setattr(
        chat_service.tokenizer,
        "continuation_completion_prompt",
        lambda messages, **kwargs: ("CONTINUE_PROMPT", ""),
    )
    monkeypatch.setattr(
        chat_service.tokenizer, "special_token_ids", lambda names: [7, 8], raising=False
    )

    async def stream(request: ChatRequest):
        calls["n"] += 1
        requests.append(request)
        if calls["n"] == 1:
            body = prev_reply
        elif calls["n"] == 2:
            body = prev_reply + "\n\n" + fresh
        else:
            body = fill
        yield ChatChunk(id="c", model="fake", delta_content=body)
        yield ChatChunk(id="c", model="fake", finish_reason="stop", prompt_tokens=10, completion_tokens=100)
        yield ChatChunk(id="c", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]

    first = [
        e
        async for e in chat_service.chat(
            message="开场", conversation_id=None, stream=True, profile="immersive",
            auto_continue=False, max_tokens=256,
        )
    ]
    cid = next(e for e in first if e.get("event") == "meta")["data"]["conversation_id"]

    events = [
        e
        async for e in chat_service.chat(
            message="继续", conversation_id=cid, stream=True, profile="immersive",
            auto_continue=True, max_tokens=6144,
        )
    ]
    done = next(e for e in events if e.get("event") == "done")["data"]
    content = done["message"]["content"]
    assert not content.startswith(prev_reply[:40]), content[:80]
    assert content.lstrip().startswith(fresh[:20])
    streamed = "".join(
        e["data"].get("content") or "" for e in events if e.get("event") == "delta"
    )
    assert prev_reply[:40] not in streamed

    first_pass, hop = requests[1], requests[2]
    assert not (first_pass.extra or {}).get("logit_bias")
    assert (hop.extra or {}).get("logit_bias") == {"7": -100.0, "8": -100.0}
    assert 256 <= hop.max_tokens <= 6144


async def test_stalled_hop_backs_up_a_sentence_instead_of_one_token(
    chat_service, fake_provider, monkeypatch
):
    """A hop whose output is fully trimmed must not resend its prompt minus one token.

    mlx-lm 0.31.3 kills its generate thread on an exact prompt-cache hit; the
    one-token-shorter prompt after a zero-progress hop hit that in live smoke.
    """
    opening = _varied(1500, "开")
    last = "她把铜钥匙放回柜台，指尖在木纹上停了一下。"
    repeat = "开0动作与呼吸变化，场景向前推进。"
    fill = _varied(4200, "续")
    sent_contents: list[str] = []
    calls = {"n": 0}

    def fake_prompt(messages, **kwargs):
        sent_contents.append(messages[-1]["content"])
        return (f"PROMPT{len(sent_contents)}", "")

    monkeypatch.setattr(chat_service.tokenizer, "continuation_completion_prompt", fake_prompt)
    monkeypatch.setattr(
        chat_service.tokenizer, "special_token_ids", lambda names: [7], raising=False
    )
    monkeypatch.setattr(chat_service.tokenizer, "first_token", lambda text: None, raising=False)

    async def stream(request: ChatRequest):
        calls["n"] += 1
        body = {1: opening + last, 2: repeat}.get(calls["n"], fill)
        yield ChatChunk(id="c", model="fake", delta_content=body)
        yield ChatChunk(id="c", model="fake", finish_reason="stop", prompt_tokens=10, completion_tokens=100)
        yield ChatChunk(id="c", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]

    events = [
        e
        async for e in chat_service.chat(
            message="继续", conversation_id=None, stream=True, profile="immersive",
            auto_continue=True, max_tokens=6144,
        )
    ]
    dones = [e["data"] for e in events if e.get("event") == "done"]
    assert dones, [e.get("event") for e in events][-5:] + [events[-1]]
    done = dones[0]
    assert len(sent_contents) >= 2
    hop1, hop2 = sent_contents[0], sent_contents[1]
    # The self-stopped first hop already resumed before its closed last sentence.
    assert hop1 == opening
    assert hop2 == drop_last_sentence(hop1) and hop2 != hop1, (hop1[-30:], hop2[-30:])
    assert count_output_chars(done["message"]["content"]) >= 5000


async def test_loop_guard_continue_marks_cut_prefix_and_turn_prompt_used(
    chat_service, fake_provider, monkeypatch
):
    """The hop after a guard cut must dodge keys mlx-lm cached but the API never sent.

    That covers the cut prefix itself (mutated=True) and the turn's original
    /v1/chat/completions prompt. An unmutated hop keeps the single-token drop.
    """
    opening = _varied(1200, "开")
    looped = "窗外的天色彻底暗了下来，只剩几盏昏黄的灯泡在尘埃里挣扎。"
    middle = "她把铜钥匙放回柜台，指尖在木纹上停了一下。"
    plain_hop = _varied(800, "中")
    fill = _varied(4200, "续")
    requests: list[ChatRequest] = []
    prompt_calls: list[dict] = []

    def fake_prompt(messages, **kwargs):
        prompt_calls.append({**kwargs, "used_prompts": list(kwargs.get("used_prompts") or [])})
        return (f"WIRE{len(prompt_calls)}", "")

    monkeypatch.setattr(chat_service.tokenizer, "continuation_completion_prompt", fake_prompt)
    monkeypatch.setattr(
        chat_service.tokenizer,
        "apply_chat_template",
        lambda messages, **kwargs: "TURN_PROMPT|" + (messages[-1].get("content") or ""),
    )
    monkeypatch.setattr(
        chat_service.tokenizer, "special_token_ids", lambda names: [7], raising=False
    )
    monkeypatch.setattr(chat_service.tokenizer, "first_token", lambda text: None, raising=False)

    async def stream(request: ChatRequest):
        requests.append(request)
        finish = "stop"
        if len(requests) == 1:
            for piece in (opening, looped, middle, "\n\n", looped, middle, looped):
                yield ChatChunk(id="c", model="fake", delta_content=piece)
        elif len(requests) == 2:
            # Ends on length so the next prefix is left untouched (a self-stop would drop a sentence).
            finish = "length"
            yield ChatChunk(id="c", model="fake", delta_content=plain_hop)
        else:
            yield ChatChunk(id="c", model="fake", delta_content=fill)
        yield ChatChunk(id="c", model="fake", finish_reason=finish, prompt_tokens=10, completion_tokens=100)
        yield ChatChunk(id="c", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]

    events = [
        e
        async for e in chat_service.chat(
            message="继续", conversation_id=None, stream=True, profile="immersive",
            auto_continue=True, max_tokens=6144,
        )
    ]
    done = next(e for e in events if e.get("event") == "done")["data"]
    assert done["guard_trim"] == "loop"
    assert len(requests) == 3
    assert len(prompt_calls) == 2

    after_cut, after_plain = prompt_calls
    assert after_cut.get("mutated") is True
    assert any(p.startswith("TURN_PROMPT|") for p in after_cut["used_prompts"])
    assert not after_plain.get("mutated")
    assert any(p.startswith("TURN_PROMPT|") for p in after_plain["used_prompts"])
    assert "WIRE1" in after_plain["used_prompts"]
    assert (requests[1].extra or {}).get("raw_prompt") == "WIRE1"
    assert (requests[2].extra or {}).get("raw_prompt") == "WIRE2"

    metas = [e["data"] for e in events if e.get("event") == "meta"]
    assert len(metas) == 3
    assert {m["message_id"] for m in metas} == {done["message"]["id"]}
    assert len([e for e in events if e.get("event") == "done"]) == 1


async def test_paragraph_cycle_is_trimmed_and_next_hop_deflects(
    chat_service, fake_provider, monkeypatch
):
    opening = _varied(1200, "开")
    looped = "窗外的天色彻底暗了下来，只剩几盏昏黄的灯泡在尘埃里挣扎。"
    middle = "她把铜钥匙放回柜台，指尖在木纹上停了一下。"
    fill = _varied(4200, "续")
    requests: list[ChatRequest] = []

    monkeypatch.setattr(
        chat_service.tokenizer,
        "continuation_completion_prompt",
        lambda messages, **kwargs: ("CONTINUE_PROMPT", ""),
    )
    monkeypatch.setattr(
        chat_service.tokenizer, "special_token_ids", lambda names: [7], raising=False
    )
    monkeypatch.setattr(
        chat_service.tokenizer, "first_token", lambda text: (99, "窗外"), raising=False
    )

    async def stream(request: ChatRequest):
        requests.append(request)
        if len(requests) == 1:
            for piece in (opening, looped, middle, "\n\n", looped, middle, looped):
                yield ChatChunk(id="c", model="fake", delta_content=piece)
        else:
            yield ChatChunk(id="c", model="fake", delta_content=fill)
        yield ChatChunk(id="c", model="fake", finish_reason="stop", prompt_tokens=10, completion_tokens=100)
        yield ChatChunk(id="c", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]

    events = [
        e
        async for e in chat_service.chat(
            message="继续", conversation_id=None, stream=True, profile="immersive",
            auto_continue=True, max_tokens=6144,
        )
    ]
    done = next(e for e in events if e.get("event") == "done")["data"]
    content = done["message"]["content"]
    assert content.count(looped) == 1, content.count(looped)
    assert done["guard_trim"] == "loop"
    assert len(requests) == 2
    assert (requests[1].extra or {}).get("logit_bias") == {"7": -100.0, "99": -100.0}
    assert count_output_chars(content) >= 5000
