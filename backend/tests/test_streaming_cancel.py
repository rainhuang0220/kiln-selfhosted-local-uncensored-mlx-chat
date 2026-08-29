import asyncio


def test_cancel_marks_assistant_cancelled(chat_service):
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


def test_non_stream_connection_error_from_provider(client, fake_provider, chat_service):
    async def boom(_request):
        raise ConnectionError("mlx connection refused")

    fake_provider.complete = boom
    r = client.post("/chat", json={"message": "hello", "stream": False})
    assert r.status_code == 502
    err = r.json()["error"]
    assert err["type"] == "api_error"
    assert err["code"] == "upstream_error"
    assert "mlx connection refused" in err["message"]

    listed = client.get("/conversation")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    cid = listed.json()["data"][0]["id"]
    detail = client.get(f"/conversation/{cid}").json()
    assistant = [m for m in detail["messages"] if m["role"] == "assistant"][-1]
    assert assistant["status"] == "error"
    assert cid not in chat_service._busy
