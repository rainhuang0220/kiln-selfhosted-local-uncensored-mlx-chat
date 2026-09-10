import asyncio

import pytest

from app.services.chat_lifecycle import RUNNING, ChatLifecycle


def test_park_failure_tries_restore(tmp_settings):
    parks: list[int] = []
    restores: list[int] = []

    async def park(_settings):
        parks.append(1)
        raise RuntimeError("lsof missing")

    async def restore(_settings):
        restores.append(1)

    life = ChatLifecycle(tmp_settings, park_fn=park, restore_fn=restore)
    with pytest.raises(RuntimeError, match="lsof missing"):
        asyncio.run(life.park("video"))
    assert parks == [1]
    assert restores == [1]
    assert life.state == RUNNING
