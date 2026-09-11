import pytest

from app.providers.sse import iter_sse_frames, parse_sse_line


def test_done_wire_is_explicit():
    frame = parse_sse_line("data: [DONE]")
    assert frame is not None
    assert frame.kind == "done"


def test_malformed_json_is_not_dropped_as_success():
    frame = parse_sse_line("data: {not-json")
    assert frame is not None
    assert frame.kind == "malformed"


def test_keepalive_comment():
    frame = parse_sse_line(": keep-alive")
    assert frame is not None
    assert frame.kind == "keepalive"


def test_finish_reason_chunk():
    frame = parse_sse_line('data: {"choices":[{"delta":{"content":"hi"},"finish_reason":"stop"}]}')
    assert frame is not None
    assert frame.kind == "json"
    assert frame.payload["choices"][0]["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_eof_without_done_yields_only_seen_frames():
    async def chunks():
        yield 'data: {"choices":[{"delta":{"content":"partial"}}]}\n'
        yield "data: {bad\n"

    kinds = [frame.kind async for frame in iter_sse_frames(chunks())]
    assert kinds == ["json", "malformed"]
    assert "done" not in kinds
