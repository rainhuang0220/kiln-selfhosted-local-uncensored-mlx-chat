from app.services.history import truncate_messages


def _est(text: str) -> int:
    return max(1, len(text) // 4)


def test_keeps_system_and_latest_user():
    messages = [
        {"id": "s", "role": "system", "content": "sys"},
        {"id": "u1", "role": "user", "content": "old " * 200},
        {"id": "a1", "role": "assistant", "content": "reply " * 200},
        {"id": "u2", "role": "user", "content": "latest question"},
    ]
    kept, dropped, truncated = truncate_messages(
        messages, budget=80, estimate=_est, reserved_output=20
    )
    assert truncated is True
    assert kept[0]["id"] == "s"
    assert kept[-1]["id"] == "u2"
    assert "u1" in dropped or "a1" in dropped


def test_no_truncation_when_under_budget():
    messages = [
        {"id": "s", "role": "system", "content": "sys"},
        {"id": "u1", "role": "user", "content": "hi"},
        {"id": "a1", "role": "assistant", "content": "hello"},
    ]
    kept, dropped, truncated = truncate_messages(
        messages, budget=10_000, estimate=_est, reserved_output=16
    )
    assert truncated is False
    assert dropped == []
    assert [m["id"] for m in kept] == ["s", "u1", "a1"]


def test_never_drops_latest_user_even_if_over():
    messages = [
        {"id": "s", "role": "system", "content": "sys"},
        {"id": "u1", "role": "user", "content": "x" * 4000},
    ]
    kept, dropped, truncated = truncate_messages(
        messages, budget=20, estimate=_est, reserved_output=8
    )
    assert kept[-1]["id"] == "u1"
    assert truncated is True or dropped == []
