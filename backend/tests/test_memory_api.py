def test_memory_stub_is_empty(client):
    r = client.get("/memory")
    assert r.status_code == 200
    body = r.json()
    assert body["data"] == []
    assert body["object"] == "list"
