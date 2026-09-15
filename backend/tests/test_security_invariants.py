"""Security invariants: private mode fail-closed, CSRF, sessions, tenant isolation."""

from __future__ import annotations

from starlette.testclient import TestClient

from app.main import create_app
from app.services import accounts
from app.services.memory import MemoryService
from app.services.memory_provider import MemoryRecord

PUBLIC_ORIGIN = "https://kiln.plainlist.space"
EVIL_ORIGIN = "https://evil.plainlist.space"


def _private_settings(tmp_settings):
    tmp_settings.kiln_exposure = "private"
    tmp_settings.cookie_secure = True
    tmp_settings.trust_proxy_headers = True
    tmp_settings.auth_signup = False
    tmp_settings.kiln_public_origin = PUBLIC_ORIGIN
    tmp_settings.session_idle_minutes = 45
    tmp_settings.session_absolute_hours = 12
    tmp_settings.session_remember_days = 7
    return tmp_settings


def _client(tmp_settings, chat_service, headers=None) -> TestClient:
    app = create_app(tmp_settings, chat=chat_service)
    return TestClient(
        app,
        base_url="https://testserver",
        headers=headers or {},
    )


def _login(c: TestClient, username="alpha", password="correct-horse", remember=False, origin=PUBLIC_ORIGIN):
    return c.post(
        "/auth/login",
        json={"username": username, "password": password, "remember_me": remember},
        headers={"Origin": origin},
    )


def _register(c: TestClient, username, password="correct-horse", origin=PUBLIC_ORIGIN):
    return c.post(
        "/auth/register",
        json={"username": username, "password": password},
        headers={"Origin": origin},
    )


def test_private_mode_zero_users_is_not_anonymously_usable(tmp_settings, chat_service):
    _private_settings(tmp_settings)
    with _client(tmp_settings, chat_service) as c:
        status = c.get("/auth/status")
        assert status.status_code == 200
        body = status.json()
        assert body["required"] is True
        assert body["ok"] is False
        assert body["username"] is None
        assert body["signup"] is False
        assert body["setup"] is False
        assert body.get("ready") is False

        for path in (
            "/conversation",
            "/memory",
            "/generate",
            "/models/local",
            "/context",
            "/v1/models",
        ):
            r = c.get(path)
            assert r.status_code in {401, 403, 404, 503}, (path, r.status_code, r.text)

        chat = c.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "ping"}]},
            headers={"Origin": PUBLIC_ORIGIN},
        )
        assert chat.status_code in {401, 403, 503}

        created = _register(c, "intruder")
        assert created.status_code in {403, 503}


def test_private_mode_refuses_insecure_cookie_at_startup(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "private"
    tmp_settings.cookie_secure = False
    try:
        create_app(tmp_settings, chat=chat_service)
        raised = False
    except RuntimeError:
        raised = True
    assert raised


def test_public_host_in_local_mode_is_forbidden_not_private(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "local"
    tmp_settings.cookie_secure = False
    with _client(
        tmp_settings,
        chat_service,
        headers={"Host": "kiln.plainlist.space"},
    ) as c:
        status = c.get("/auth/status")
        assert status.status_code == 403
        assert status.json()["error"]["code"] == "local_mode_violation"
        assert c.get("/conversation").status_code == 403


def test_anonymous_private_endpoints_401_after_owner_exists(tmp_settings, chat_service):
    _private_settings(tmp_settings)
    accounts.create_user("alpha", "correct-horse")
    with _client(tmp_settings, chat_service) as c:
        assert c.get("/auth/status").json()["required"] is True
        assert c.get("/conversation").status_code == 401
        assert c.get("/memory").status_code == 401
        assert c.get("/generate").status_code == 401
        assert c.get("/models/local").status_code == 401
        r = c.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "ping"}]},
            headers={"Origin": PUBLIC_ORIGIN},
        )
        assert r.status_code == 401


def test_logout_invalidates_old_cookie(tmp_settings, chat_service):
    _private_settings(tmp_settings)
    accounts.create_user("alpha", "correct-horse")
    with _client(tmp_settings, chat_service) as c:
        assert _login(c).status_code == 200
        assert c.get("/conversation").status_code == 200
        token = c.cookies.get(accounts.cookie_name(secure=True)) or c.cookies.get("kiln_session")
        assert token
        assert c.post("/auth/logout", headers={"Origin": PUBLIC_ORIGIN}).status_code == 200
        assert c.get("/conversation").status_code == 401
        c.cookies.set(accounts.cookie_name(secure=True), token)
        c.cookies.set("kiln_session", token)
        assert c.get("/conversation").status_code == 401


def test_idle_timeout_invalidates_session(tmp_settings, chat_service, monkeypatch):
    _private_settings(tmp_settings)
    tmp_settings.session_idle_minutes = 1
    accounts.create_user("alpha", "correct-horse")
    now = {"t": 1_700_000_000_000}

    def fake_now():
        return now["t"]

    monkeypatch.setattr(accounts, "_now", fake_now)
    with _client(tmp_settings, chat_service) as c:
        assert _login(c).status_code == 200
        assert c.get("/conversation").status_code == 200
        now["t"] += 2 * 60 * 1000
        assert c.get("/conversation").status_code == 401


def test_absolute_timeout_invalidates_session(tmp_settings, chat_service, monkeypatch):
    _private_settings(tmp_settings)
    tmp_settings.session_absolute_hours = 1
    tmp_settings.session_idle_minutes = 10_000
    accounts.create_user("alpha", "correct-horse")
    now = {"t": 1_700_000_000_000}
    monkeypatch.setattr(accounts, "_now", lambda: now["t"])
    with _client(tmp_settings, chat_service) as c:
        assert _login(c).status_code == 200
        now["t"] += 2 * 3600 * 1000
        assert c.get("/conversation").status_code == 401


def test_remember_me_false_is_non_persistent_cookie(tmp_settings, chat_service):
    _private_settings(tmp_settings)
    accounts.create_user("alpha", "correct-horse")
    with _client(tmp_settings, chat_service) as c:
        r = _login(c, remember=False)
        assert r.status_code == 200
        header = r.headers.get("set-cookie", "")
        assert "Max-Age" not in header
        assert "HttpOnly" in header or "httponly" in header.lower()
        assert "Secure" in header or "secure" in header.lower()
        assert "samesite=strict" in header.lower()
        assert "Domain=" not in header
        assert "Path=/" in header
        assert header.lower().startswith("__host-kiln_session=") or "__Host-kiln_session=" in header


def test_remember_me_true_is_bounded_persistent_cookie(tmp_settings, chat_service):
    _private_settings(tmp_settings)
    accounts.create_user("alpha", "correct-horse")
    with _client(tmp_settings, chat_service) as c:
        r = _login(c, remember=True)
        assert r.status_code == 200
        header = r.headers.get("set-cookie", "")
        assert "Max-Age=" in header
        max_age = int(
            [p for p in header.split(";") if p.strip().lower().startswith("max-age=")][0].split("=")[1]
        )
        assert 6 * 24 * 3600 <= max_age <= 8 * 24 * 3600


def test_csrf_wrong_origin_forbidden(tmp_settings, chat_service):
    _private_settings(tmp_settings)
    accounts.create_user("alpha", "correct-horse")
    with _client(tmp_settings, chat_service) as c:
        assert _login(c).status_code == 200
        r = c.post("/auth/logout", headers={"Origin": EVIL_ORIGIN})
        assert r.status_code == 403
        r = c.delete("/conversation/00000000-0000-0000-0000-000000000001", headers={"Origin": EVIL_ORIGIN})
        assert r.status_code == 403
        # session still valid because logout was rejected
        assert c.get("/conversation").status_code == 200


def test_tenant_isolation_conversations_and_memory(tmp_settings, chat_service):
    _private_settings(tmp_settings)
    tmp_settings.auth_signup = True
    accounts.create_user("alpha", "correct-horse")
    accounts.create_user("beta", "correct-horse")
    with _client(tmp_settings, chat_service) as a, _client(tmp_settings, chat_service) as b:
        assert _login(a, "alpha").status_code == 200
        assert _login(b, "beta").status_code == 200
        chat_a = a.post(
            "/chat",
            json={"message": "alpha-only ping", "stream": False},
            headers={"Origin": PUBLIC_ORIGIN},
        )
        assert chat_a.status_code == 200, chat_a.text
        cid = chat_a.json()["conversation_id"]
        mem = a.post(
            "/memory",
            json={"content": "secret-A", "key": "slot", "memory_type": "fact"},
            headers={"Origin": PUBLIC_ORIGIN},
        )
        assert mem.status_code == 200, mem.text
        mid = mem.json()["id"]

        listed_b = b.get("/conversation")
        assert listed_b.status_code == 200
        assert listed_b.json()["total"] == 0
        assert b.get(f"/conversation/{cid}").status_code == 404
        assert b.get("/memory", params={"q": "secret"}).json()["data"] == []
        assert b.get(f"/memory/{mid}").status_code == 404
        assert b.patch(
            f"/memory/{mid}",
            json={"content": "hacked"},
            headers={"Origin": PUBLIC_ORIGIN},
        ).status_code == 404
        assert b.delete(f"/memory/{mid}", headers={"Origin": PUBLIC_ORIGIN}).status_code == 404

        listed_a = a.get("/memory", params={"q": "secret"})
        assert any(row["content"] == "secret-A" for row in listed_a.json()["data"])


def test_memory_cannot_enter_other_owner_prompt(tmp_settings, chat_service):
    mem: MemoryService = chat_service.memory
    mem.save(
        MemoryRecord(
            id="",
            memory_type="fact",
            key="secret-a",
            content="secret-A",
            importance=0.99,
            user_id="user-a",
        )
    )
    mem.save(
        MemoryRecord(
            id="",
            memory_type="fact",
            key="secret-b",
            content="secret-B",
            importance=0.99,
            user_id="user-b",
        )
    )
    a_hits = mem.retrieve_for_prompt("secret", 256, owner_id="user-a")
    b_hits = mem.retrieve_for_prompt("secret", 256, owner_id="user-b")
    assert [h.content for h in a_hits] == ["secret-A"]
    assert [h.content for h in b_hits] == ["secret-B"]
    assert mem.retrieve_for_prompt("secret", 256, owner_id=None) == []
    assert mem.delete(a_hits[0].id, owner_id="user-b") is False
    assert mem.update(a_hits[0].id, owner_id="user-b", content="nope") is None


def test_legacy_null_owner_rows_assign_only_to_bootstrap_owner(tmp_settings, chat_service):
    conn = accounts.get_conn()
    conn.execute(
        """
        INSERT INTO conversations (
          id, title, model, system_prompt, settings_json, created_at, updated_at, user_id
        ) VALUES ('legacy-conv', 'legacy', 'm', '', '{}', 1, 1, NULL)
        """
    )
    conn.execute(
        """
        INSERT INTO memories (
          id, memory_type, key, content, importance, confidence, status, created_at, updated_at, user_id
        ) VALUES ('legacy-mem', 'fact', 'k', 'legacy-memory', 0.5, 0.5, 'active', 1, 1, NULL)
        """
    )
    conn.commit()
    owner = accounts.ensure_bootstrap("owner", "correct-horse")
    assert owner is not None
    row = conn.execute("SELECT user_id FROM conversations WHERE id='legacy-conv'").fetchone()
    assert row["user_id"] == owner.id
    mem = conn.execute("SELECT user_id FROM memories WHERE id='legacy-mem'").fetchone()
    assert mem["user_id"] == owner.id
    second = accounts.ensure_bootstrap("other", "correct-horse")
    assert second is None


def test_non_owner_cannot_manage_models(tmp_settings, chat_service):
    _private_settings(tmp_settings)
    tmp_settings.model_downloads_enabled = True
    tmp_settings.model_switch_enabled = True
    accounts.create_user("alpha", "correct-horse")
    accounts.create_user("beta", "correct-horse")
    with _client(tmp_settings, chat_service) as owner, _client(tmp_settings, chat_service) as user:
        assert _login(owner, "alpha").status_code == 200
        assert _login(user, "beta").status_code == 200
        denied = user.post(
            "/models/download",
            json={"repo_id": "mlx-community/example"},
            headers={"Origin": PUBLIC_ORIGIN},
        )
        assert denied.status_code in {401, 403, 404}
        local = user.get("/models/local")
        assert local.status_code in {200, 401, 403, 404}
        if local.status_code == 200:
            # listing may be allowed; activate must not
            act = user.post(
                "/models/example/activate",
                headers={"Origin": PUBLIC_ORIGIN},
            )
            assert act.status_code in {401, 403, 404}


def test_authenticated_responses_are_not_stored_in_shared_cache(tmp_settings, chat_service):
    _private_settings(tmp_settings)
    accounts.create_user("alpha", "correct-horse")
    with _client(tmp_settings, chat_service) as c:
        assert _login(c).status_code == 200
        r = c.get("/conversation")
        cc = r.headers.get("cache-control", "").lower()
        assert "no-store" in cc
        assert "private" in cc


def test_health_does_not_leak_internal_urls_when_private(tmp_settings, chat_service):
    _private_settings(tmp_settings)
    accounts.create_user("alpha", "correct-horse")
    with _client(tmp_settings, chat_service) as c:
        r = c.get("/health")
        # unauthenticated health is public-exact today; private mode should hide internals
        body = r.json()
        provider = body.get("provider") or {}
        assert provider.get("base_url") in {"", None}
        text = r.text
        assert "127.0.0.1" not in text
        assert "/Users/" not in text
        assert "chat.db" not in text


def _local_client(tmp_settings, chat_service, host: str) -> TestClient:
    tmp_settings.kiln_exposure = "local"
    tmp_settings.cookie_secure = False
    app = create_app(tmp_settings, chat=chat_service)
    return TestClient(app, base_url=f"http://{host}", headers={"Host": host})


def test_zero_users_loopback_hosts_may_stay_open(tmp_settings, chat_service):
    for host in ("127.0.0.1", "localhost"):
        with _local_client(tmp_settings, chat_service, host) as c:
            body = c.get("/auth/status").json()
            assert body["required"] is False, host
            assert body["ok"] is True, host
            assert c.get("/conversation").status_code == 200, host


def test_zero_users_ipv6_loopback_host_may_stay_open(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "local"
    tmp_settings.cookie_secure = False
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app, base_url="http://127.0.0.1", headers={"Host": "[::1]"}) as c:
        body = c.get("/auth/status").json()
        assert body["required"] is False
        assert c.get("/conversation").status_code == 200


def test_zero_users_rfc1918_and_link_local_hosts_fail_closed(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "local"
    tmp_settings.cookie_secure = False
    for host in ("192.168.1.10", "10.0.0.2", "172.16.0.2", "169.254.1.1"):
        with _local_client(tmp_settings, chat_service, host) as c:
            assert c.get("/auth/status").status_code == 403, host
            assert c.get("/conversation").status_code == 403, host


def test_zero_users_arbitrary_hostname_fail_closed(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "local"
    tmp_settings.cookie_secure = False
    for host in ("kiln.internal", "macbook.local", "anything", "127.evil.com"):
        with _local_client(tmp_settings, chat_service, host) as c:
            assert c.get("/auth/status").status_code == 403, host
            assert c.get("/conversation").status_code == 403, host


def test_trusted_https_proxy_does_not_honor_spoofed_loopback_host(tmp_settings, chat_service):
    tmp_settings.kiln_exposure = "local"
    tmp_settings.cookie_secure = False
    tmp_settings.trust_proxy_headers = True
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(
        app,
        base_url="http://127.0.0.1",
        headers={"Host": "127.0.0.1", "X-Forwarded-Proto": "https"},
    ) as c:
        r = c.get("/auth/status")
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "local_mode_violation"
        assert c.get("/conversation").status_code == 403


def test_private_exposure_ignores_loopback_host(tmp_settings, chat_service):
    _private_settings(tmp_settings)
    app = create_app(tmp_settings, chat=chat_service)
    for host in ("127.0.0.1", "localhost", "[::1]", "192.168.1.10"):
        with TestClient(app, base_url="https://127.0.0.1", headers={"Host": host}) as c:
            body = c.get("/auth/status").json()
            assert body["required"] is True, host
            assert body["ok"] is False, host
            assert c.get("/conversation").status_code in {401, 403, 503}, host
