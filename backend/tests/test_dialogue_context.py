from app.services.dialogue_context import DialogueState, build_dialogue_context, group_turns


def _turns(n: int, *, facts: dict[int, str] | None = None) -> list[dict]:
    facts = facts or {}
    msgs = [{"id": "s", "role": "system", "content": "persona stays put"}]
    for i in range(n):
        extra = facts.get(i, "")
        msgs.append({"id": f"u{i}", "role": "user", "content": f"user turn {i}。{extra}"})
        msgs.append({"id": f"a{i}", "role": "assistant", "content": f"assistant turn {i}。继续往前走。"})
    return msgs


def test_group_turns_keeps_user_assistant_pairs():
    msgs = _turns(3)
    system, turns = group_turns(msgs)
    assert len(system) == 1
    assert len(turns) == 3
    assert [m["role"] for m in turns[0]] == ["user", "assistant"]


def test_does_not_split_a_logical_turn():
    msgs = _turns(12, facts={0: "地点：旧书店 约定：周五见面 事件：丢了钥匙 偏好：不喝美式 还没给地址"})
    built = build_dialogue_context(
        msgs,
        budget=80,
        estimate=lambda t: max(1, len(t) // 4),
        recent_turn_target=4,
        min_recent_turns=2,
        fold_every_turns=4,
    )
    roles = [m["role"] for m in built.messages if m.get("id") != "dialogue-context"]
    paired = [r for r in roles if r != "system"]
    assert paired[0] in {"user", "system"}
    # After dropping context card, remaining non-system messages should not end on a lone assistant.
    rest = [m for m in built.messages if m.get("role") != "system" and m.get("id") != "dialogue-context"]
    if rest and rest[0]["role"] == "assistant":
        raise AssertionError("leading half-turn")
    if rest and rest[-1]["role"] == "assistant" and rest[-2]["role"] != "user":
        raise AssertionError("broken pairing")
    assert built.compressed is True
    assert built.state.location == "旧书店"
    assert any("周五" in fact for fact in built.state.established_facts)
    assert any("钥匙" in fact for fact in built.state.established_facts)
    assert any("不喝美式" in p or "美式" in p for p in built.state.user_preferences + built.state.established_facts)
    assert built.state.open_threads
    assert any(m.get("id") == "dialogue-context" for m in built.messages)
    recent_ids = [m["id"] for m in built.messages if m.get("id") not in {"s", "dialogue-context"}]
    assert "u0" not in recent_ids
    assert recent_ids[-2].startswith("u")
    assert recent_ids[-1].startswith("a")


def test_summary_does_not_rewrite_when_under_budget():
    msgs = _turns(2)
    prior = DialogueState(location="旧书店")
    first = build_dialogue_context(
        msgs,
        budget=10_000,
        estimate=lambda t: 1,
        prior_state=prior,
        prior_summary="keep-me",
    )
    assert first.compressed is False
    assert first.summary == "keep-me"
    assert first.state.location == "旧书店"
    assert not any(m.get("id") == "dialogue-context" for m in first.messages)


def test_does_not_fold_under_token_budget_just_because_turns_exceed_target():
    built = build_dialogue_context(
        _turns(12),
        budget=50_000,
        estimate=lambda t: 1,
        recent_turn_target=4,
        min_recent_turns=4,
        fold_every_turns=4,
    )
    assert built.compressed is False
    assert not any(m.get("id") == "dialogue-context" for m in built.messages)
    assert built.recent_turns == 12


def test_old_context_is_not_reinjected_into_every_user_turn():
    msgs = _turns(10, facts={0: "地点：港口"})
    built = build_dialogue_context(
        msgs,
        budget=160,
        estimate=lambda t: max(1, len(t) // 4),
        recent_turn_target=3,
        min_recent_turns=2,
    )
    users = [m for m in built.messages if m.get("role") == "user" and m.get("id") != "dialogue-context"]
    assert users
    assert all("<dialogue_state>" not in (u.get("content") or "") for u in users)
    assert all("<history_summary>" not in (u.get("content") or "") for u in users)
