"""Audit simulations for Kiln SSE reassembly on this commit.

Mirrors the current code. Assertions describe what HEAD does, including defects.
Does not import the web bundle and does not modify backend/ or web/.
"""

from __future__ import annotations

import asyncio
import codecs
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend" / "app"


def load(name: str, rel: str):
    path = BACKEND / rel
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sse = load("kiln_sse", "providers/sse.py")
ledger_mod = load("kiln_ledger", "services/stream_protocol.py")
continuation = load("kiln_continuation", "services/continuation.py")
heartbeat = load("kiln_heartbeat", "services/heartbeat.py")

StreamLedger = ledger_mod.StreamLedger
TerminalState = ledger_mod.TerminalState


def test_split_utf8_survives_line_buffer() -> None:
    """httpx TextDecoder holds a partial code point; iter_sse_frames joins lines."""
    payload = 'data: {"choices":[{"index":0,"delta":{"content":"你好"}}]}\n\n'
    raw = payload.encode("utf-8")
    split_at = raw.index("你".encode()) + 1  # first byte of 你 only
    assert split_at < len(raw)

    async def chunks():
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        for piece in (raw[:split_at], raw[split_at:]):
            text = decoder.decode(piece)
            if text:
                yield text
        tail = decoder.decode(b"", True)
        if tail:
            yield tail

    frames = asyncio.run(_collect(sse.iter_sse_frames(chunks())))
    assert [frame.kind for frame in frames] == ["json"]
    assert frames[0].payload["choices"][0]["delta"]["content"] == "你好"
    assert "\ufffd" not in json.dumps(frames[0].payload, ensure_ascii=False)


def test_string_chunks_do_not_parse_a_partial_line() -> None:
    async def chunks():
        yield 'data: {"choices":[{"delta":{"content":"你'
        yield '好"}}]}\n\n'

    frames = asyncio.run(_collect(sse.iter_sse_frames(chunks())))
    assert len(frames) == 1
    assert frames[0].payload["choices"][0]["delta"]["content"] == "你好"


def test_eof_does_not_invent_done() -> None:
    async def chunks():
        yield 'data: {"choices":[{"delta":{"content":"partial"}}]}\n'

    frames = asyncio.run(_collect(sse.iter_sse_frames(chunks())))
    assert [frame.kind for frame in frames] == ["json"]
    book = StreamLedger(http_eof=True)
    book.observe_finish("stop")
    assert book.classify() is TerminalState.INTERRUPTED_TRANSPORT
    assert book.stored_finish_reason() == "interrupted_transport"


def test_finish_plus_done_is_stop_even_with_a_dropped_malformed_frame() -> None:
    """Defect: a skipped bad frame does not block completed_stop."""
    book = StreamLedger(malformed_frames=1)
    book.observe_finish("stop")
    book.observe_done_wire()
    assert book.classify() is TerminalState.COMPLETED_STOP
    assert book.incomplete() is False


def test_duplicate_and_out_of_order_ids_append_in_arrival_order() -> None:
    """id: lines are ignored. Same payload twice is appended twice. No reorder."""
    wire = (
        "id: 2\n"
        'data: {"id":"c","choices":[{"index":1,"delta":{"content":"B"}}]}\n'
        "\n"
        "id: 2\n"
        'data: {"id":"c","choices":[{"index":0,"delta":{"content":"B"}}]}\n'
        "\n"
        "id: 1\n"
        'data: {"id":"c","choices":[{"index":0,"delta":{"content":"A"}}]}\n'
        "\n"
    )

    async def chunks():
        yield wire

    frames = asyncio.run(_collect(sse.iter_sse_frames(chunks())))
    texts = []
    for frame in frames:
        # mlx.py _chunk_from_event uses choices[0] and ignores index / SSE id.
        choice = frame.payload["choices"][0]
        delta = choice.get("delta") or {}
        text = choice.get("text") or delta.get("content")
        if text:
            texts.append(text)
    assert texts == ["B", "B", "A"]
    assert "".join(texts) == "BBA"


def test_tail_stripper_drops_a_diverging_prefix() -> None:
    """A partial tail match is returned when the next chunk diverges."""
    stripper = continuation.TailStripper("ing")
    assert stripper.feed("i") == ""
    assert stripper.feed("dea") == "idea"
    assert continuation.strip_regenerated_tail("idea", "ing") == "idea"
    aligned = continuation.TailStripper("ing")
    assert aligned.feed("i") == ""
    assert aligned.feed("ng more") == " more"


def test_client_reassembly_utf8_duplicate_order_and_crlf() -> None:
    events = _read_sse_bytes(_chunks_of('event: delta\ndata: {"content":"你好"}\n\n', size=3))
    assert _visible(events) == "你好"
    assert events[-1] == {"event": "transport_eof", "data": {"reason": "eof"}}

    dup = _read_sse_bytes(
        [
            (
                'event: delta\ndata: {"content":"甲"}\n\n'
                'event: delta\ndata: {"content":"甲"}\n\n'
                'event: done\ndata: {"finish_reason":"stop","terminal_state":"completed_stop",'
                '"incomplete":false,"message":{"content":"甲甲"}}\n\n'
                "data: [DONE]\n\n"
            ).encode()
        ]
    )
    assert _visible(dup) == "甲甲"
    assert dup[-1]["event"] == "done_wire" or any(ev["event"] == "done" for ev in dup)
    assert not any(ev["event"] == "transport_eof" for ev in dup)

    # CR and LF of the data-line terminator fall in different chunks.
    # JSON.parse accepts the trailing CR, so the delta is kept. Kiln itself writes LF.
    body = 'event: delta\r\ndata: {"content":"雨"}\r\n\r\n'
    crlf_at = body.rfind("\r\n\r\n")
    assert body[crlf_at : crlf_at + 4] == "\r\n\r\n"
    part_a = body[: crlf_at + 1].encode()
    part_b = body[crlf_at + 1 :].encode()
    split_crlf = _read_sse_bytes([part_a, part_b])
    assert _visible(split_crlf) == "雨"

    eof = _read_sse_bytes(['event: delta\ndata: {"content":"partial"}\n\n'.encode()])
    assert _visible(eof) == "partial"
    assert eof[-1] == {"event": "transport_eof", "data": {"reason": "eof"}}

    late = _read_sse_bytes(
        [
            (
                'event: delta\ndata: {"content":"A"}\n\n'
                'event: done\ndata: {"finish_reason":"stop","incomplete":false,"message":{"content":"Z"}}\n\n'
                'event: delta\ndata: {"content":"Q"}\n\n'
            ).encode()
        ]
    )
    # done writes the store from message.content but does not replace the local accumulator.
    # A later delta appends to the pre-done buffer and overwrites the authoritative text.
    assert _reduce_client(late) == "AQ"


def test_disconnect_closes_nested_generators() -> None:
    closed = {"provider": False, "chat": False}

    async def provider():
        try:
            await asyncio.sleep(30)
            yield "tok"
        finally:
            closed["provider"] = True

    async def consume_stream(agen):
        try:
            async for chunk in agen:
                yield {"event": "delta", "data": {"content": chunk}}
        finally:
            closer = getattr(agen, "aclose", None)
            if closer is not None:
                await closer()

    async def chat():
        try:
            async for event in consume_stream(provider()):
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            raise
        finally:
            closed["chat"] = True

    async def event_stream():
        stream = heartbeat.iterate_with_heartbeats(chat(), 0.05)
        try:
            async for event in stream:
                yield event
        except (asyncio.CancelledError, GeneratorExit):
            await stream.aclose()
            raise

    async def main():
        agen = event_stream()
        first = await agen.__anext__()
        assert first["event"] == "ping"
        await agen.aclose()
        leftover = [
            task
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task() and not task.done()
        ]
        assert leftover == []

    asyncio.run(main())
    assert closed == {"provider": True, "chat": True}


async def _collect(agen):
    out = []
    async for item in agen:
        out.append(item)
    return out


def _chunks_of(text: str, size: int) -> list[bytes]:
    raw = text.encode("utf-8")
    return [raw[i : i + size] for i in range(0, len(raw), size)]


def _parse_block(raw: str) -> dict | None:
    event = "message"
    data_lines: list[str] = []
    for line in raw.split("\n"):
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    data = "\n".join(data_lines)
    if not data:
        return None
    if data == "[DONE]":
        return {"event": "done_wire", "data": "[DONE]"}
    try:
        return {"event": event, "data": json.loads(data)}
    except json.JSONDecodeError:
        return {"event": event, "data": data}


def _read_sse_bytes(chunks: list[bytes]) -> list[dict]:
    """Faithful port of web/src/api/stream.ts readSse, including per-chunk CRLF replace."""
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    buf = ""
    saw_app_done = False
    out: list[dict] = []

    def flush(chunk: str) -> list[dict]:
        nonlocal buf
        buf += chunk.replace("\r\n", "\n")
        events: list[dict] = []
        while True:
            idx = buf.find("\n\n")
            if idx < 0:
                break
            raw = buf[:idx]
            buf = buf[idx + 2 :]
            parsed = _parse_block(raw)
            if parsed:
                events.append(parsed)
        return events

    def note(ev: dict) -> dict:
        nonlocal saw_app_done
        if ev["event"] == "done":
            saw_app_done = True
        return ev

    def take(ev: dict) -> bool:
        if ev["event"] == "done_wire":
            if not saw_app_done:
                out.append({"event": "transport_eof", "data": {"reason": "done_wire"}})
            return True
        if ev["event"] == "ping":
            out.append(ev)
            return False
        out.append(note(ev))
        return False

    for value in chunks:
        for ev in flush(decoder.decode(value)):
            if take(ev):
                return out
    for ev in flush(decoder.decode(b"", True)):
        if take(ev):
            return out
    if buf.strip():
        parsed = _parse_block(buf)
        if parsed and parsed["event"] != "done_wire":
            out.append(note(parsed))
    if not saw_app_done:
        out.append({"event": "transport_eof", "data": {"reason": "eof"}})
    return out


def _visible(events: list[dict]) -> str:
    return _reduce_client(events)


def _reduce_client(events: list[dict], initial: str = "") -> str:
    """chat-store.ts: local accumulator is not replaced on done; set() is."""
    content = initial
    shown = initial
    for ev in events:
        data = ev["data"]
        if ev["event"] == "delta" and isinstance(data, dict) and data.get("content"):
            content += data["content"]
            shown = content
        elif ev["event"] == "done" and isinstance(data, dict):
            message = data.get("message") or {}
            authored = message.get("content") if isinstance(message, dict) else None
            shown = content if authored is None else authored
        elif ev["event"] == "delta" and isinstance(data, str):
            pass
    return shown


if __name__ == "__main__":
    tests = [
        test_split_utf8_survives_line_buffer,
        test_string_chunks_do_not_parse_a_partial_line,
        test_eof_does_not_invent_done,
        test_finish_plus_done_is_stop_even_with_a_dropped_malformed_frame,
        test_duplicate_and_out_of_order_ids_append_in_arrival_order,
        test_tail_stripper_drops_a_diverging_prefix,
        test_client_reassembly_utf8_duplicate_order_and_crlf,
        test_disconnect_closes_nested_generators,
    ]
    for test in tests:
        test()
        print(f"ok {test.__name__}")
    print(f"ok {len(tests)} tests")
