from app.services.compress import compress_messages, extractive_summary


def test_extractive_summary_skips_system():
    s = extractive_summary(
        [
            {"role": "system", "content": "hidden"},
            {"role": "user", "content": "hello world"},
            {"role": "assistant", "content": "hi there"},
        ]
    )
    assert "hidden" not in s
    assert "hello" in s


def test_compress_under_budget_is_noop():
    msgs = [
        {"id": "s", "role": "system", "content": "sys"},
        {"id": "u", "role": "user", "content": "hi"},
    ]
    kept, summary, compressed = compress_messages(
        msgs, budget=10_000, estimate=lambda t: 1, reserved_output=10
    )
    assert compressed is False
    assert summary is None
    assert [m["id"] for m in kept] == ["s", "u"]


def test_compress_folds_old_turns():
    msgs = [{"id": "s", "role": "system", "content": "sys"}]
    for i in range(20):
        msgs.append({"id": f"u{i}", "role": "user", "content": "x" * 80})
        msgs.append({"id": f"a{i}", "role": "assistant", "content": "y" * 80})
    kept, summary, compressed = compress_messages(
        msgs, budget=200, estimate=lambda t: max(1, len(t) // 4), reserved_output=20, recent_keep=4
    )
    assert compressed is True
    assert summary
    roles = [m["role"] for m in kept]
    assert roles[0] == "system"
    assert "user" in roles
    assert any("<history_summary>" in (m.get("content") or "") for m in kept)