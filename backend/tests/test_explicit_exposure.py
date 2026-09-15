"""Exposure is explicit config. Host/user_count never select the mode."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.main import create_app
from app.services import accounts


def test_unset_exposure_refuses_startup(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = None
    with pytest.raises(RuntimeError, match="KILN_EXPOSURE"):
        create_app(tmp_settings, chat=chat_service)


def test_empty_exposure_refuses_startup(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = ""
    with pytest.raises(RuntimeError, match="KILN_EXPOSURE"):
        create_app(tmp_settings, chat=chat_service)


def test_private_always_requires_auth_even_on_loopback_and_zero_users(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "private"
    tmp_settings.cookie_secure = True
    tmp_settings.kiln_public_origin = "https://kiln.plainlist.space"
    app = create_app(tmp_settings, chat=chat_service)
    for host in ("127.0.0.1", "localhost", "[::1]", "192.168.1.1", "kiln.plainlist.space"):
        with TestClient(app, base_url="https://127.0.0.1", headers={"Host": host}) as c:
            body = c.get("/auth/status").json()
            assert body["required"] is True, host
            assert body["exposure"] == "private", host
            assert body["ready"] is False, host
            assert c.get("/conversation").status_code in {401, 403, 503}, host


def test_local_public_host_is_forbidden_not_a_mode_switch(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "local"
    tmp_settings.cookie_secure = False
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(
        app, base_url="http://127.0.0.1", headers={"Host": "kiln.plainlist.space"}
    ) as c:
        status = c.get("/auth/status")
        assert status.status_code == 403
        assert status.json().get("error", {}).get("code") == "local_mode_violation"
        conv = c.get("/conversation")
        assert conv.status_code == 403


def test_local_forwarded_public_host_is_forbidden(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "local"
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"Host": "127.0.0.1", "X-Forwarded-Host": "kiln.plainlist.space"},
    ) as c:
        assert c.get("/conversation").status_code == 403


def test_local_https_proxy_headers_are_forbidden_not_private_open(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "local"
    tmp_settings.trust_proxy_headers = True
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"Host": "127.0.0.1", "X-Forwarded-Proto": "https"},
    ) as c:
        r = c.get("/conversation")
        assert r.status_code == 403
        assert r.json().get("error", {}).get("code") == "local_mode_violation"


def test_local_lan_host_is_forbidden(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "local"
    app = create_app(tmp_settings, chat=chat_service)
    for host in ("192.168.1.1", "10.0.0.2", "172.16.0.2", "169.254.1.1"):
        with TestClient(app, base_url="http://127.0.0.1", headers={"Host": host}) as c:
            assert c.get("/auth/status").status_code == 403, host


def test_testserver_host_is_not_production_loopback(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "local"
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app) as c:
        # Starlette default Host is testserver
        r = c.get("/auth/status")
        assert r.status_code == 403
        assert r.json().get("error", {}).get("code") == "local_mode_violation"


def test_local_user_count_does_not_enable_auth(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "local"
    accounts.create_user("rain", "correct-horse")
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        body = c.get("/auth/status").json()
        assert body["required"] is False
        assert body["exposure"] == "local"
        assert c.get("/conversation").status_code == 200


def test_private_csrf_rejects_loopback_origin(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "private"
    tmp_settings.cookie_secure = True
    tmp_settings.kiln_public_origin = "https://kiln.plainlist.space"
    accounts.create_user("rain", "correct-horse")
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app, base_url="https://kiln.plainlist.space") as c:
        login = c.post(
            "/auth/login",
            json={"username": "rain", "password": "correct-horse", "remember_me": False},
            headers={"Origin": "https://kiln.plainlist.space"},
        )
        assert login.status_code == 200, login.text
        evil = c.post(
            "/auth/logout",
            json={},
            headers={"Origin": "http://127.0.0.1:7777"},
        )
        assert evil.status_code == 403
        localhost = c.post(
            "/auth/logout",
            json={},
            headers={"Origin": "http://localhost:8787"},
        )
        assert localhost.status_code == 403
        missing = c.post("/auth/logout", json={}, headers={"Origin": ""})
        # TestClient may omit empty Origin; still must reject
        assert missing.status_code == 403


def test_private_requires_https_public_origin(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "private"
    tmp_settings.cookie_secure = True
    tmp_settings.kiln_public_origin = "http://kiln.plainlist.space"
    with pytest.raises(RuntimeError, match="KILN_PUBLIC_ORIGIN"):
        create_app(tmp_settings, chat=chat_service)
    tmp_settings.kiln_public_origin = "https://kiln.plainlist.space/app"
    with pytest.raises(RuntimeError, match="KILN_PUBLIC_ORIGIN"):
        create_app(tmp_settings, chat=chat_service)
