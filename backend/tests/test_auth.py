def test_auth_disabled_when_no_users(client):
    r = client.get("/auth/status")
    assert r.status_code == 200
    body = r.json()
    assert body["required"] is False
    assert body["ok"] is True
    assert body["setup"] is True


def test_username_password_session(tmp_settings, chat_service):
    from starlette.testclient import TestClient

    from app.main import create_app
    from app.services import accounts

    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app) as c:
        reg = c.post(
            "/auth/register",
            json={"username": "rain", "password": "correct-horse"},
        )
        assert reg.status_code == 200, reg.text
        assert reg.json()["username"] == "rain"
        assert "kiln_session" in c.cookies

        status = c.get("/auth/status")
        assert status.json()["required"] is True
        assert status.json()["ok"] is True
        assert status.json()["username"] == "rain"

        chat = c.post("/chat", json={"message": "hello", "stream": False})
        assert chat.status_code == 200, chat.text
        cid = chat.json()["conversation_id"]

        listed = c.get("/conversation")
        assert listed.json()["total"] == 1

        c.post("/auth/logout")
        denied = c.post("/chat", json={"message": "nope", "stream": False})
        assert denied.status_code == 401

        bad = c.post(
            "/auth/login",
            json={"username": "rain", "password": "wrong-password-xx"},
        )
        assert bad.status_code == 401

        ok = c.post(
            "/auth/login",
            json={"username": "rain", "password": "correct-horse"},
        )
        assert ok.status_code == 200
        again = c.get(f"/conversation/{cid}")
        assert again.status_code == 200

        other = accounts.create_user("other", "correct-horse")
        token = accounts.create_session(other.id)
        c.cookies.set("kiln_session", token)
        steal = c.get(f"/conversation/{cid}")
        assert steal.status_code == 404

        health = c.get("/health")
        assert health.json()["provider"]["base_url"] == ""

    tmp_settings.max_request_bytes = 1024
    app_small = create_app(tmp_settings, chat=chat_service)
    with TestClient(app_small) as c2:
        c2.post("/auth/login", json={"username": "rain", "password": "correct-horse"})
        huge = c2.post("/chat", content=b"x" * 2000, headers={"Content-Length": "2000"})
        assert huge.status_code == 413


def test_signup_disabled_after_first_user(tmp_settings, chat_service):
    from starlette.testclient import TestClient

    from app.main import create_app

    tmp_settings.auth_signup = False
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app) as c:
        first = c.post(
            "/auth/register",
            json={"username": "alpha", "password": "correct-horse"},
        )
        assert first.status_code == 200
        second = c.post(
            "/auth/register",
            json={"username": "beta", "password": "correct-horse"},
        )
        assert second.status_code == 403


def test_short_password_rejected(client):
    r = client.post("/auth/register", json={"username": "rain", "password": "short"})
    assert r.status_code == 400


def test_locked_account_cannot_have_its_lock_extended(tmp_settings, chat_service, monkeypatch):
    from starlette.testclient import TestClient

    from app.main import create_app
    from app.services import accounts

    now = 1_700_000_000_000
    monkeypatch.setattr(accounts, "_now", lambda: now)
    tmp_settings.login_per_minute = accounts.LOCK_AFTER + 2
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app) as c:
        c.post(
            "/auth/register",
            json={"username": "rain", "password": "correct-horse"},
        )
        for _ in range(accounts.LOCK_AFTER):
            r = c.post(
                "/auth/login",
                json={"username": "rain", "password": "wrong-password-xx"},
            )
            assert r.status_code == 401

        row = accounts.get_conn().execute(
            "SELECT failed_logins, locked_until FROM users WHERE username='rain'"
        ).fetchone()
        assert row["failed_logins"] == accounts.LOCK_AFTER
        locked_until = row["locked_until"]

        r = c.post(
            "/auth/login",
            json={"username": "rain", "password": "wrong-password-xx"},
        )
        assert r.status_code == 401
        row = accounts.get_conn().execute(
            "SELECT failed_logins, locked_until FROM users WHERE username='rain'"
        ).fetchone()
        assert row["failed_logins"] == accounts.LOCK_AFTER
        assert row["locked_until"] == locked_until


def test_login_rate_limit_uses_proxy_client_ip_only_when_trusted(tmp_settings, chat_service):
    from starlette.testclient import TestClient

    from app.main import create_app
    from app.services import accounts

    accounts.create_user("rain", "correct-horse")
    tmp_settings.login_per_minute = 1
    tmp_settings.trust_proxy_headers = True
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app) as c:
        first = c.post(
            "/auth/login",
            json={"username": "rain", "password": "wrong-password-xx"},
            headers={"X-Real-IP": "198.51.100.10"},
        )
        assert first.status_code == 401

        blocked = c.post(
            "/auth/login",
            json={"username": "rain", "password": "wrong-password-xx"},
            headers={"X-Real-IP": "198.51.100.10"},
        )
        assert blocked.status_code == 429

        other_client = c.post(
            "/auth/login",
            json={"username": "rain", "password": "wrong-password-xx"},
            headers={"X-Real-IP": "198.51.100.11"},
        )
        assert other_client.status_code == 401
