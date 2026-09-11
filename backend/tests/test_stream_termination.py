import asyncio

from app.providers.base import ChatChunk, ChatRequest, ChatResult


def _assistant(chat_service, cid):
    detail = chat_service.get_conversation(cid)
    return [m for m in detail["messages"] if m["role"] == "assistant"][-1]


def test_eof_before_done_is_not_complete(chat_service, fake_provider):
    async def eof(_request: ChatRequest):
        yield ChatChunk(id="x", model="fake", delta_content="partial reply")
        yield ChatChunk(id="x", model="fake", http_eof=True)

    fake_provider.stream = eof  # type: ignore[method-assign]

    async def run():
        events = []
        async for ev in chat_service.chat(message="hi", conversation_id=None, stream=True):
            events.append(ev)
        return events

    events = asyncio.run(run())
    done = next(ev for ev in events if ev["event"] == "done")
    assert done["data"]["terminal_state"] == "interrupted_transport"
    assert done["data"]["incomplete"] is True
    assert done["data"]["message"]["content"] == "partial reply"
    cid = next(ev for ev in events if ev["event"] == "meta")["data"]["conversation_id"]
    asst = _assistant(chat_service, cid)
    assert asst["status"] == "error"
    assert asst["finish_reason"] == "interrupted_transport"
    assert asst["content"] == "partial reply"


def test_done_without_finish_is_protocol_error(chat_service, fake_provider):
    async def done_only(_request: ChatRequest):
        yield ChatChunk(id="x", model="fake", delta_content="hello")
        yield ChatChunk(id="x", model="fake", wire_done=True)

    fake_provider.stream = done_only  # type: ignore[method-assign]
    events = asyncio.run(
        _collect(chat_service.chat(message="hi", conversation_id=None, stream=True))
    )
    done = next(ev for ev in events if ev["event"] == "done")
    assert done["data"]["terminal_state"] == "upstream_protocol_error"
    cid = next(ev for ev in events if ev["event"] == "meta")["data"]["conversation_id"]
    assert _assistant(chat_service, cid)["status"] == "error"


def test_finish_length_is_classified(chat_service, fake_provider):
    async def length(_request: ChatRequest):
        yield ChatChunk(id="x", model="fake", delta_content="cut")
        yield ChatChunk(id="x", model="fake", finish_reason="length")
        yield ChatChunk(id="x", model="fake", wire_done=True)

    fake_provider.stream = length  # type: ignore[method-assign]
    events = asyncio.run(
        _collect(chat_service.chat(message="hi", conversation_id=None, stream=True))
    )
    done = next(ev for ev in events if ev["event"] == "done")
    assert done["data"]["terminal_state"] == "completed_length"
    assert done["data"]["finish_reason"] == "length"
    cid = next(ev for ev in events if ev["event"] == "meta")["data"]["conversation_id"]
    assert _assistant(chat_service, cid)["status"] == "complete"


def test_malformed_frames_then_eof(chat_service, fake_provider):
    async def bad(_request: ChatRequest):
        yield ChatChunk(id="x", model="fake", malformed=True)
        yield ChatChunk(id="x", model="fake", malformed=True)
        yield ChatChunk(id="x", model="fake", http_eof=True)

    fake_provider.stream = bad  # type: ignore[method-assign]
    events = asyncio.run(
        _collect(chat_service.chat(message="hi", conversation_id=None, stream=True))
    )
    done = next(ev for ev in events if ev["event"] == "done")
    assert done["data"]["terminal_state"] == "upstream_protocol_error"


def test_usage_only_final_chunk_still_needs_finish(chat_service, fake_provider):
    async def usage(_request: ChatRequest):
        yield ChatChunk(id="x", model="fake", delta_content="ok")
        yield ChatChunk(id="x", model="fake", prompt_tokens=9, completion_tokens=2, cached_tokens=1)
        yield ChatChunk(id="x", model="fake", finish_reason="stop")
        yield ChatChunk(id="x", model="fake", wire_done=True)

    fake_provider.stream = usage  # type: ignore[method-assign]
    events = asyncio.run(
        _collect(chat_service.chat(message="hi", conversation_id=None, stream=True))
    )
    done = next(ev for ev in events if ev["event"] == "done")
    assert done["data"]["terminal_state"] == "completed_stop"
    assert done["data"]["usage"]["cached_tokens"] == 1


def test_zero_token_upstream_is_unknown_or_error(chat_service, fake_provider):
    async def empty(_request: ChatRequest):
        yield ChatChunk(id="x", model="fake", wire_done=True)

    fake_provider.stream = empty  # type: ignore[method-assign]
    events = asyncio.run(
        _collect(chat_service.chat(message="hi", conversation_id=None, stream=True))
    )
    done = next(ev for ev in events if ev["event"] == "done")
    assert done["data"]["terminal_state"] != "completed_stop"
    cid = next(ev for ev in events if ev["event"] == "meta")["data"]["conversation_id"]
    assert _assistant(chat_service, cid)["status"] != "complete"


def test_repetition_guard_keeps_text(chat_service, fake_provider):
    loop = "他抬起头看向窗外。" * 3

    async def looping(_request: ChatRequest):
        yield ChatChunk(id="x", model="fake", delta_content=loop)

    fake_provider.stream = looping  # type: ignore[method-assign]
    events = asyncio.run(
        _collect(chat_service.chat(message="hi", conversation_id=None, stream=True))
    )
    done = next(ev for ev in events if ev["event"] == "done")
    assert done["data"]["terminal_state"] == "repetition_guard"
    assert "窗外" in done["data"]["message"]["content"]


def test_continue_does_not_insert_user_message(chat_service, fake_provider):
    async def first(_request: ChatRequest):
        yield ChatChunk(id="x", model="fake", delta_content="partial")
        yield ChatChunk(id="x", model="fake", http_eof=True)

    async def more(request: ChatRequest):
        fake_provider.calls.append(request)
        tail = request.extra.get("continue_dropped_tail") or ""
        yield ChatChunk(id="x", model="fake", delta_content=f"{tail} more")
        yield ChatChunk(id="x", model="fake", finish_reason="stop")
        yield ChatChunk(id="x", model="fake", wire_done=True)

    fake_provider.stream = first  # type: ignore[method-assign]
    events = asyncio.run(
        _collect(chat_service.chat(message="hello there", conversation_id=None, stream=True))
    )
    cid = next(ev for ev in events if ev["event"] == "meta")["data"]["conversation_id"]
    fake_provider.stream = more  # type: ignore[method-assign]
    asyncio.run(
        _collect(
            chat_service.chat(
                message="",
                conversation_id=cid,
                stream=True,
                continue_generation=True,
            )
        )
    )
    detail = chat_service.get_conversation(cid)
    users = [m for m in detail["messages"] if m["role"] == "user"]
    assistants = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert len(users) == 1
    assert len(assistants) == 1
    assert assistants[0]["content"] == "partial more"
    req = fake_provider.calls[-1]
    prompt = req.extra.get("raw_prompt") or ""
    assert prompt
    assert "<|im_start|>user\ncontinue" not in prompt
    assert req.extra.get("continue_dropped_tail") is not None


async def _collect(agen):
    return [ev async for ev in agen]


def test_non_stream_missing_finish_is_not_stop(chat_service, fake_provider):
    async def complete(request: ChatRequest) -> ChatResult:
        fake_provider.calls.append(request)
        return ChatResult(
            id="x",
            model="fake",
            content="ok",
            reasoning="",
            finish_reason=None,
            prompt_tokens=3,
            completion_tokens=1,
            cached_tokens=0,
            usage_source="upstream",
        )

    fake_provider.complete = complete  # type: ignore[method-assign]
    events = asyncio.run(
        _collect(chat_service.chat(message="hi", conversation_id=None, stream=False))
    )
    done = next(ev for ev in events if ev["event"] == "done")
    assert done["data"]["terminal_state"] == "upstream_protocol_error"
    assert done["data"]["finish_reason"] != "stop"
