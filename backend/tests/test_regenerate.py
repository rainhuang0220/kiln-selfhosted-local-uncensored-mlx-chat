def test_regenerate_drops_last_assistant(client):
    r = client.post("/chat", json={"message": "first", "stream": False})
    cid = r.json()["conversation_id"]
    before = client.get(f"/conversation/{cid}").json()
    asst = [m for m in before["messages"] if m["role"] == "assistant"]
    assert len(asst) == 1
    r2 = client.post(
        "/chat",
        json={"message": "", "conversation_id": cid, "regenerate": True, "stream": False},
    )
    assert r2.status_code == 200, r2.text
    after = client.get(f"/conversation/{cid}").json()
    asst2 = [m for m in after["messages"] if m["role"] == "assistant"]
    users = [m for m in after["messages"] if m["role"] == "user"]
    assert len(users) == 1
    assert len(asst2) == 1
    assert asst2[0]["id"] != asst[0]["id"]