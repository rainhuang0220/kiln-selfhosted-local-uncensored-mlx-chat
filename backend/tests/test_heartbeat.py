import asyncio

from app.services.heartbeat import iterate_with_heartbeats


def test_heartbeat_emits_ping_while_waiting():
    async def slow():
        await asyncio.sleep(0.12)
        yield {"event": "delta", "data": {"content": "x"}}

    async def run():
        events = [
            ev
            async for ev in iterate_with_heartbeats(slow(), 0.03, ping={"event": "ping", "data": {}})
        ]
        assert any(ev["event"] == "ping" for ev in events)
        assert events[-1]["event"] == "delta"

    asyncio.run(run())
