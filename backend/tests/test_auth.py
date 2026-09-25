def test_change_password_revokes_sessions(tmp_settings, chat_service):
    from starlette.testclient import TestClient

    from app.main import create_app
    from app.services import accounts

    user = accounts.create_user("rain", "correct-horse")
    token = accounts.create_session(user.id)
    assert accounts.resolve_session(token) is not None
    accounts.change_password("rain", "correct-horse", "new-horse-battery")
    assert accounts.resolve_session(token) is None
    assert accounts.authenticate("rain", "correct-horse") is None
    assert accounts.authenticate("rain", "new-horse-battery") is not None

    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        bad = c.post(
            "/auth/login",
            json={"username": "rain", "password": "correct-horse"},
            headers={"Origin": "http://127.0.0.1:8787"},
        )
        assert bad.status_code == 401


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

    origin = "https://kiln.plainlist.space"
    tmp_settings.kiln_exposure = "private"
    tmp_settings.cookie_secure = True
    tmp_settings.kiln_public_origin = origin
    accounts.create_user("rain", "correct-horse")
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app, base_url=origin) as c:
        assert c.get("/auth/runtime").status_code == 401
        ok = c.post(
            "/auth/login",
            json={"username": "rain", "password": "correct-horse", "remember_me": False},
            headers={"Origin": origin},
        )
        assert ok.status_code == 200, ok.text
        assert "__Host-kiln_session" in (c.cookies.keys() | set()) or any(
            "kiln_session" in n for n in c.cookies.keys()
        )

        status = c.get("/auth/status")
        assert status.json()["required"] is True
        assert status.json()["ok"] is True
        assert status.json()["username"] == "rain"
        runtime = c.get("/auth/runtime")
        assert runtime.status_code == 200
        assert runtime.json()["provider"]["base_url"] == ""
        assert runtime.json()["gateway"]["state"] == "AVAILABLE"

        chat = c.post(
            "/chat",
            json={"message": "hello", "stream": False},
            headers={"Origin": origin},
        )
        assert chat.status_code == 200, chat.text
        cid = chat.json()["conversation_id"]

        listed = c.get("/conversation")
        assert listed.json()["total"] == 1

        c.post("/auth/logout", json={}, headers={"Origin": origin})
        denied = c.post(
            "/chat",
            json={"message": "nope", "stream": False},
            headers={"Origin": origin},
        )
        assert denied.status_code == 401

        bad = c.post(
            "/auth/login",
            json={"username": "rain", "password": "wrong-password-xx"},
            headers={"Origin": origin},
        )
        assert bad.status_code == 401

        ok = c.post(
            "/auth/login",
            json={"username": "rain", "password": "correct-horse", "remember_me": False},
            headers={"Origin": origin},
        )
        assert ok.status_code == 200
        again = c.get(f"/conversation/{cid}")
        assert again.status_code == 200

        other = accounts.create_user("other", "correct-horse")
        token = accounts.create_session(other.id)
        c.cookies.clear()
        steal = c.get(
            f"/conversation/{cid}",
            headers={"Cookie": f"__Host-kiln_session={token}"},
        )
        assert steal.status_code == 404

        health = c.get("/health")
        assert health.json()["provider"]["base_url"] == ""

    tmp_settings.max_request_bytes = 1024
    app_small = create_app(tmp_settings, chat=chat_service)
    with TestClient(app_small, base_url=origin) as c2:
        c2.post(
            "/auth/login",
            json={"username": "rain", "password": "correct-horse", "remember_me": False},
            headers={"Origin": origin},
        )
        huge = c2.post("/chat", content=b"x" * 2000, headers={"Content-Length": "2000", "Origin": origin})
        assert huge.status_code == 413


def test_signup_disabled_after_first_user(tmp_settings, chat_service):
    from starlette.testclient import TestClient

    from app.main import create_app

    tmp_settings.auth_signup = False
    tmp_settings.kiln_exposure = "local"
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        origin = "http://127.0.0.1:8787"
        first = c.post(
            "/auth/register",
            json={"username": "alpha", "password": "correct-horse"},
            headers={"Origin": origin},
        )
        assert first.status_code == 200
        second = c.post(
            "/auth/register",
            json={"username": "beta", "password": "correct-horse"},
            headers={"Origin": origin},
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
    origin = "http://127.0.0.1:8787"
    with TestClient(app, base_url="http://127.0.0.1") as c:
        c.post(
            "/auth/register",
            json={"username": "rain", "password": "correct-horse"},
            headers={"Origin": origin},
        )
        for _ in range(accounts.LOCK_AFTER):
            r = c.post(
                "/auth/login",
                json={"username": "rain", "password": "wrong-password-xx"},
                headers={"Origin": origin},
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
            headers={"Origin": origin},
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
    origin = "http://127.0.0.1:8787"
    with TestClient(app, base_url="http://127.0.0.1") as c:
        first = c.post(
            "/auth/login",
            json={"username": "rain", "password": "wrong-password-xx"},
            headers={"X-Real-IP": "198.51.100.10", "Origin": origin},
        )
        assert first.status_code == 401

        blocked = c.post(
            "/auth/login",
            json={"username": "rain", "password": "wrong-password-xx"},
            headers={"X-Real-IP": "198.51.100.10", "Origin": origin},
        )
        assert blocked.status_code == 429

        other_client = c.post(
            "/auth/login",
            json={"username": "rain", "password": "wrong-password-xx"},
            headers={"X-Real-IP": "198.51.100.11", "Origin": origin},
        )
        assert other_client.status_code == 401
