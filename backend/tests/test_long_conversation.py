def test_fifty_turns_list_and_message_count(client):
    first = client.post("/chat", json={"message": "turn 1", "stream": False})
    assert first.status_code == 200, first.text
    cid = first.json()["conversation_id"]

    for n in range(2, 51):
        r = client.post(
            "/chat",
            json={"message": f"turn {n}", "conversation_id": cid, "stream": False},
        )
        assert r.status_code == 200, r.text

    listed = client.get("/conversation")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] >= 1
    row = next(item for item in body["data"] if item["id"] == cid)
    assert row["message_count"] == 100

    detail = client.get(f"/conversation/{cid}")
    assert detail.status_code == 200
    conv = detail.json()
    assert conv["message_count"] == 100
    roles = [m["role"] for m in conv["messages"]]
    assert "system" not in roles
    assert roles[0] == "user"
    assert roles.count("user") == 50
    assert roles.count("assistant") == 50
