import asyncio

from app.providers.base import ChatChunk, ChatRequest


def test_thinking_false_never_calls_manual_continuation(chat_service, fake_provider):
    async def long_think(request: ChatRequest):
        fake_provider.calls.append(request)
        yield ChatChunk(id="x", model="fake", delta_reasoning="plan " * 400)
        yield ChatChunk(id="x", model="fake", delta_content="visible")
        yield ChatChunk(id="x", model="fake", finish_reason="stop")
        yield ChatChunk(id="x", model="fake", wire_done=True)

    fake_provider.stream = long_think  # type: ignore[method-assign]
    after = []

    async def forbidden(*_a, **_k):
        after.append(1)
        yield ChatChunk(id="x", model="fake", delta_content="should-not")

    fake_provider.stream_after_think = forbidden  # type: ignore[method-assign]

    async def run():
        return [
            ev
            async for ev in chat_service.chat(
                message="hi",
                conversation_id=None,
                stream=True,
                enable_thinking=False,
                max_tokens=64,
            )
        ]

    events = asyncio.run(run())
    text = "".join(
        (ev["data"].get("content") or "") for ev in events if ev["event"] == "delta"
    )
    assert "visible" in text
    assert after == []
    assert fake_provider.calls[0].enable_thinking is False


def test_thinking_true_without_continuation_stays_on_chat_completions(
    chat_service, fake_provider
):
    async def native(request: ChatRequest):
        fake_provider.calls.append(request)
        yield ChatChunk(id="x", model="fake", delta_reasoning="plan")
        yield ChatChunk(id="x", model="fake", delta_content="answer")
        yield ChatChunk(id="x", model="fake", finish_reason="stop")
        yield ChatChunk(id="x", model="fake", wire_done=True)

    called = []

    async def forbidden(*_a, **_k):
        called.append(1)
        if False:
            yield ChatChunk(id="x", model="fake")

    fake_provider.stream = native  # type: ignore[method-assign]
    fake_provider.stream_after_think = forbidden  # type: ignore[method-assign]
    events = asyncio.run(
        _collect(
            chat_service.chat(
                message="hi",
                conversation_id=None,
                stream=True,
                enable_thinking=True,
                thinking_continuation=False,
                max_tokens=64,
            )
        )
    )
    done = next(ev for ev in events if ev["event"] == "done")
    assert done["data"]["message"]["content"] == "answer"
    assert called == []
    assert fake_provider.calls[0].enable_thinking is True


async def _collect(agen):
    return [ev async for ev in agen]


def test_unclosed_think_is_split_and_not_continued_by_default(chat_service, fake_provider):
    async def unclosed(_request: ChatRequest):
        yield ChatChunk(id="x", model="fake", delta_content="<think>plan only")
        yield ChatChunk(id="x", model="fake", finish_reason="stop")
        yield ChatChunk(id="x", model="fake", wire_done=True)

    after = []

    async def forbidden(*_a, **_k):
        after.append(1)
        if False:
            yield ChatChunk(id="x", model="fake")

    fake_provider.stream = unclosed  # type: ignore[method-assign]
    fake_provider.stream_after_think = forbidden  # type: ignore[method-assign]
    events = asyncio.run(
        _collect(
            chat_service.chat(
                message="hi",
                conversation_id=None,
                stream=True,
                enable_thinking=True,
                thinking_continuation=False,
                max_tokens=64,
            )
        )
    )
    done = next(ev for ev in events if ev["event"] == "done")
    assert after == []
    assert done["data"]["message"]["reasoning_content"]
    assert done["data"]["terminal_state"] == "completed_stop"


def test_provider_eof_during_reasoning_is_interrupted(chat_service, fake_provider):
    async def eof_think(_request: ChatRequest):
        yield ChatChunk(id="x", model="fake", delta_reasoning="still thinking")
        yield ChatChunk(id="x", model="fake", http_eof=True)

    fake_provider.stream = eof_think  # type: ignore[method-assign]
    events = asyncio.run(
        _collect(
            chat_service.chat(
                message="hi",
                conversation_id=None,
                stream=True,
                enable_thinking=True,
                thinking_continuation=False,
            )
        )
    )
    done = next(ev for ev in events if ev["event"] == "done")
    assert done["data"]["terminal_state"] == "interrupted_transport"
    assert done["data"]["incomplete"] is True
    assert "still thinking" in done["data"]["message"]["reasoning_content"]


def test_max_tokens_during_visible_output_is_length(chat_service, fake_provider):
    async def length_visible(_request: ChatRequest):
        yield ChatChunk(id="x", model="fake", delta_reasoning="plan")
        yield ChatChunk(id="x", model="fake", delta_content="visible cut")
        yield ChatChunk(id="x", model="fake", finish_reason="length")
        yield ChatChunk(id="x", model="fake", wire_done=True)

    fake_provider.stream = length_visible  # type: ignore[method-assign]
    events = asyncio.run(
        _collect(
            chat_service.chat(
                message="hi",
                conversation_id=None,
                stream=True,
                enable_thinking=True,
                thinking_continuation=False,
            )
        )
    )
    done = next(ev for ev in events if ev["event"] == "done")
    assert done["data"]["terminal_state"] == "completed_length"
    assert done["data"]["message"]["content"] == "visible cut"


def test_continue_mid_think_does_not_close_think(chat_service, fake_provider):
    async def cut(_request: ChatRequest):
        yield ChatChunk(id="x", model="fake", delta_reasoning="half plan")
        yield ChatChunk(id="x", model="fake", http_eof=True)

    async def resume(request: ChatRequest):
        fake_provider.calls.append(request)
        yield ChatChunk(id="x", model="fake", delta_reasoning=" more plan")
        yield ChatChunk(id="x", model="fake", finish_reason="stop")
        yield ChatChunk(id="x", model="fake", wire_done=True)

    fake_provider.stream = cut  # type: ignore[method-assign]
    events = asyncio.run(
        _collect(
            chat_service.chat(
                message="hi",
                conversation_id=None,
                stream=True,
                enable_thinking=True,
                thinking_continuation=False,
            )
        )
    )
    cid = next(ev for ev in events if ev["event"] == "meta")["data"]["conversation_id"]
    fake_provider.stream = resume  # type: ignore[method-assign]
    asyncio.run(
        _collect(
            chat_service.chat(
                message="",
                conversation_id=cid,
                stream=True,
                continue_generation=True,
                enable_thinking=True,
            )
        )
    )
    prompt = fake_provider.calls[-1].extra.get("raw_prompt") or ""
    assert prompt.endswith("<think>\nhalf plan\n")
    assert not prompt.rstrip().endswith("</think>")
