import pytest


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "", "stream": False},
        {"message": "   ", "stream": False},
        {"stream": False},
    ],
)
def test_empty_message_returns_400(client, payload):
    r = client.post("/chat", json=payload)
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["type"] == "invalid_request_error"
    assert err["code"] == "invalid_body"


def test_missing_conversation_returns_404(client):
    missing = "00000000-0000-0000-0000-000000000000"
    r = client.post(
        "/chat",
        json={
            "message": "hello",
            "conversation_id": missing,
            "stream": False,
        },
    )
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "conversation_not_found"
    assert err["type"] == "not_found_error"

    detail = client.get(f"/conversation/{missing}")
    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "conversation_not_found"


def test_oversized_message_returns_400(tmp_settings, chat_service):
    from starlette.testclient import TestClient

    from app.main import create_app

    tmp_settings.max_message_chars = 100
    app = create_app(tmp_settings, chat=chat_service)
    with TestClient(app) as c:
        r = c.post("/chat", json={"message": "x" * 101, "stream": False})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "invalid_body"
    assert err["param"] == "message"
    assert "too long" in err["message"]
