import asyncio

import pytest
from starlette.testclient import TestClient

from app.main import create_app
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


def test_injected_chat_stays_available_when_mlx_restore_fails(
    tmp_settings, chat_service, monkeypatch
):
    """TestClient with a fake chat must not inherit live-worker recovery_failed."""
    monkeypatch.setattr("app.services.media_runtime._health_ok", lambda _url: False)

    def boom(_settings):
        raise RuntimeError("mlx restore unavailable")

    monkeypatch.setattr("app.services.media_runtime.restore_mlx", boom)
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        r = c.post("/chat", json={"message": "hi", "stream": False})
        assert r.status_code != 503
        assert r.json().get("code") != "CHAT_MODEL_PARKED"
        assert r.status_code == 200
