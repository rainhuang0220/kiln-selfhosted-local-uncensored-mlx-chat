"""Deterministic 50-turn protocol/context harness. No live model quality gate."""

from app.services.dialogue_context import build_dialogue_context


def test_fifty_turns_are_classified_and_ordered(client):
    first = client.post("/chat", json={"message": "地点：旧书店。约定：周五见面。", "stream": False})
    assert first.status_code == 200, first.text
    cid = first.json()["conversation_id"]
    assert first.json()["finish_reason"]
    assert first.json().get("message")

    for n in range(2, 51):
        payload = {"message": f"turn {n}", "conversation_id": cid, "stream": False}
        if n == 8:
            payload["message"] = "事件：丢了钥匙。还没给地址。"
        if n == 9:
            payload["message"] = "偏好：不喝美式。"
        r = client.post("/chat", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["finish_reason"] not in {None, "unknown_terminal"}
        assert body["message"]["role"] == "assistant"

    detail = client.get(f"/conversation/{cid}").json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles[0] == "user"
    assert roles.count("user") == 50
    assert roles.count("assistant") == 50
    for i in range(0, 100, 2):
        assert roles[i] == "user"
        assert roles[i + 1] == "assistant"
    unknown = [
        m
        for m in detail["messages"]
        if m["role"] == "assistant" and m["status"] == "complete" and m["finish_reason"] in {None, "unknown_terminal"}
    ]
    assert unknown == []


def test_compression_keeps_early_state_and_full_recent_turns():
    msgs = [{"id": "s", "role": "system", "content": "persona"}]
    msgs.append(
        {
            "id": "u0",
            "role": "user",
            "content": "地点：旧书店 约定：周五见面 事件：丢了钥匙 偏好：不喝美式 还没给地址",
        }
    )
    msgs.append({"id": "a0", "role": "assistant", "content": "记下了。"})
    for i in range(1, 24):
        msgs.append({"id": f"u{i}", "role": "user", "content": f"later {i} " + ("话" * 40)})
        msgs.append({"id": f"a{i}", "role": "assistant", "content": f"reply {i} " + ("答" * 40)})
    built = build_dialogue_context(
        msgs,
        budget=220,
        estimate=lambda t: max(1, len(t) // 4),
        recent_turn_target=6,
        min_recent_turns=4,
        fold_every_turns=4,
    )
    assert built.compressed is True
    assert built.state.location == "旧书店"
    assert any("周五" in fact for fact in built.state.established_facts)
    rest = [m for m in built.messages if m.get("id") not in {"s", "dialogue-context"}]
    assert rest[-2]["role"] == "user"
    assert rest[-1]["role"] == "assistant"
    users = [m for m in rest if m["role"] == "user"]
    assert all("<history_summary>" not in (u.get("content") or "") for u in users)
