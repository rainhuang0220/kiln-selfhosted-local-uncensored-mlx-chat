"""Local-only owner password recovery. No HTTP endpoint. No env password."""

from __future__ import annotations

import pytest

from app.services import accounts


def test_reset_password_rejects_unknown_user(tmp_settings):
    with pytest.raises(ValueError, match="user not found"):
        accounts.reset_password("missing", "new-horse-battery")


def test_reset_password_rejects_non_owner(tmp_settings):
    accounts.create_user("owner", "correct-horse")
    accounts.create_user("member", "correct-horse")
    with pytest.raises(ValueError, match="owner"):
        accounts.reset_password("member", "new-horse-battery")


def test_reset_password_changes_hash_and_revokes_sessions(tmp_settings):
    user = accounts.create_user("rain", "correct-horse")
    token = accounts.create_session(user.id)
    assert accounts.resolve_session(token) is not None
    names = accounts.list_api_token_names(user.id)
    assert names == []

    accounts.reset_password("rain", "new-horse-battery")

    assert accounts.authenticate("rain", "correct-horse") is None
    assert accounts.authenticate("rain", "new-horse-battery") is not None
    assert accounts.resolve_session(token) is None


def test_reset_password_cli_uses_getpass_twice_not_env(tmp_settings, monkeypatch, capsys):
    from app import cli

    monkeypatch.setattr(cli, "settings", tmp_settings)
    accounts.create_user("rain", "correct-horse")
    monkeypatch.setenv("KILN_NEW_PASSWORD", "from-env-must-be-ignored")
    prompts: list[str] = []

    def fake_getpass(prompt=""):
        prompts.append(prompt)
        return "typed-horse-battery"

    monkeypatch.setattr(cli.getpass, "getpass", fake_getpass)
    cli.main(["reset-password", "--username", "rain"])
    out = capsys.readouterr().out
    assert "password reset; sessions revoked" in out
    assert "from-env-must-be-ignored" not in out
    assert "typed-horse-battery" not in out
    assert len(prompts) == 2
    assert accounts.authenticate("rain", "from-env-must-be-ignored") is None
    assert accounts.authenticate("rain", "typed-horse-battery") is not None


def test_reset_password_cli_rejects_mismatch(tmp_settings, monkeypatch):
    from app import cli

    monkeypatch.setattr(cli, "settings", tmp_settings)
    accounts.create_user("rain", "correct-horse")
    values = iter(["first-password-xx", "second-password-yy"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(values))
    with pytest.raises(SystemExit):
        cli.main(["reset-password", "--username", "rain"])
    assert accounts.authenticate("rain", "correct-horse") is not None


def test_no_http_password_reset_route(tmp_settings, chat_service):
    from starlette.testclient import TestClient

    from app.main import create_app

    tmp_settings.kiln_exposure = "private"
    tmp_settings.cookie_secure = True
    tmp_settings.kiln_public_origin = "https://kiln.plainlist.space"
    app = create_app(tmp_settings, chat=chat_service)
    paths = {getattr(r, "path", "") for r in app.routes}
    assert not any("reset" in p.lower() and "password" in p.lower() for p in paths)
    with TestClient(app, base_url="https://testserver") as c:
        r = c.post("/auth/reset-password", json={"username": "rain", "password": "x"})
        assert r.status_code in {401, 404, 405}
