def test_low_effort_cuts_long_thinking(tmp_settings, fake_provider, client):
    from app.providers.base import ChatChunk, ChatRequest

    async def long_think(request: ChatRequest):
        fake_provider.calls.append(request)
        yield ChatChunk(
            id="chatcmpl-fake",
            model="qwen3.8-27b",
            delta_reasoning=("plan " * 400),
        )
        yield ChatChunk(
            id="chatcmpl-fake",
            model="qwen3.8-27b",
            delta_content="should-not-appear",
        )

    fake_provider.stream = long_think  # type: ignore[method-assign]
    tmp_settings.thinking_budget_low = 32
    with client.stream(
        "POST",
        "/chat",
        json={
            "message": "hi",
            "stream": True,
            "enable_thinking": True,
            "reasoning_effort": "low",
            "max_tokens": 64,
        },
    ) as r:
        text = "".join(r.iter_text())
        assert r.status_code == 200, text
    assert "should-not-appear" not in text
    assert "answer-after-think" in text
    assert "plan" in text


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model"] == "qwen3.5-9b-hauhau-aggressive-mxfp4"
    assert body["practical_prompt_budget"] >= 32768
    assert body["default_max_tokens"] >= 8192
    assert body["max_tokens_cap"] >= 32768


def test_ten_thousand_chars_reach_the_model(client, fake_provider):
    blob = "甲" * 10_000
    r = client.post(
        "/chat",
        json={
            "message": blob + "\n只复述最后一个字。",
            "stream": False,
            "enable_thinking": False,
            "max_tokens": 64,
        },
    )
    assert r.status_code == 200, r.text
    user = fake_provider.calls[-1].messages[-1]
    assert user["role"] == "user"
    assert user["content"].count("甲") == 10_000
    snap = r.json()["context"]["occupancy"]
    assert not (snap.get("document_pack") or {}).get("applied")


def test_huge_file_is_packed_into_budget(tmp_settings, chat_service, fake_provider):
    from starlette.testclient import TestClient

    from app.main import create_app

    tmp_settings.practical_prompt_budget = 800
    app = create_app(tmp_settings, chat=chat_service)
    body = "请摘要。\n# File: big.txt\n" + ("段落内容 unique-needle-xyz " * 4000)
    with TestClient(app) as c:
        r = c.post(
            "/chat",
            json={"message": body, "stream": False, "enable_thinking": False, "max_tokens": 32},
        )
        assert r.status_code == 200, r.text
    user = fake_provider.calls[-1].messages[-1]["content"]
    assert user.startswith("请摘要。")
    assert "<document packed=\"true\"" in user
    pack = r.json()["context"]["occupancy"]["document_pack"]
    assert pack["applied"] is True
    assert pack["original_tokens"] > pack["kept_tokens"]


def test_chat_non_stream_roundtrip(client):
    r = client.post("/chat", json={"message": "hello kiln", "stream": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] is True
    assert body["message"]["role"] == "assistant"
    assert "echo:hello kiln" in body["message"]["content"]
    assert body["usage"]["prompt_tokens"] == 12
    cid = body["conversation_id"]

    listed = client.get("/conversation")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["data"][0]["id"] == cid

    detail = client.get(f"/conversation/{cid}")
    assert detail.status_code == 200
    roles = [m["role"] for m in detail.json()["messages"]]
    assert "system" not in roles
    assert roles[0] == "user"
    assert "user" in roles and "assistant" in roles

    ctx = client.get(f"/conversation/{cid}/context")
    assert ctx.status_code == 200
    payload = ctx.json()["payload"]
    assert payload["messages"][-1]["role"] == "user"
    assert payload["messages"][-1]["content"] == "hello kiln"
    assert all(m.get("role") != "system" for m in payload["messages"])
    assert not (ctx.json().get("effective_system_prompt") or "").strip()

    r2 = client.post(
        "/chat",
        json={"message": "second turn", "conversation_id": cid, "stream": False},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["created"] is False
    detail2 = client.get(f"/conversation/{cid}")
    user_msgs = [m for m in detail2.json()["messages"] if m["role"] == "user"]
    assert len(user_msgs) == 2


def test_delete_message_removes_a_complete_turn(client):
    created = client.post("/chat", json={"message": "remove this turn", "stream": False})
    assert created.status_code == 200, created.text
    conversation_id = created.json()["conversation_id"]
    messages = client.get(f"/conversation/{conversation_id}").json()["messages"]
    user_id = next(message["id"] for message in messages if message["role"] == "user")

    removed = client.delete(f"/conversation/{conversation_id}/message/{user_id}")

    assert removed.status_code == 204
    remaining = client.get(f"/conversation/{conversation_id}").json()["messages"]
    assert remaining == []


def test_chat_stream_sse(client):
    with client.stream("POST", "/chat", json={"message": "stream me", "stream": True}) as r:
        assert r.status_code == 200
        text = "".join(r.iter_text())
    assert "event: meta" in text
    assert "event: snapshot" in text
    assert "event: delta" in text
    assert "event: done" in text
    assert "echo:stream me" in text


def test_conversation_search(client):
    client.post("/chat", json={"message": "alpha unique kiln phrase", "stream": False})
    client.post("/chat", json={"message": "beta other topic", "stream": False})
    all_rows = client.get("/conversation").json()["data"]
    hit = client.get("/conversation", params={"q": "unique kiln"}).json()
    assert hit["total"] >= 1
    assert any("unique kiln" in (r.get("title") or "") or "unique kiln" in (r.get("last_message_preview") or "") for r in hit["data"])
    assert hit["total"] <= len(all_rows)


def test_delete_conversation(client):
    r = client.post("/chat", json={"message": "bye", "stream": False})
    cid = r.json()["conversation_id"]
    d = client.delete(f"/conversation/{cid}")
    assert d.status_code == 204
    missing = client.get(f"/conversation/{cid}")
    assert missing.status_code == 404


def test_cancel_marks_assistant_cancelled(chat_service):
    import asyncio

    async def run():
        agen = chat_service.chat(message="hold", conversation_id=None, stream=True)
        ev = await agen.__anext__()
        assert ev["event"] == "meta"
        cid = ev["data"]["conversation_id"]
        await agen.aclose()
        detail = chat_service.get_conversation(cid)
        assistant = [m for m in detail["messages"] if m["role"] == "assistant"][-1]
        assert assistant["status"] == "cancelled"
        assert cid not in chat_service._busy

    asyncio.run(run())


def test_openai_compat_stateless(client, fake_provider):
    r = client.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "chat.completion"
    assert "echo:ping" in body["choices"][0]["message"]["content"]
