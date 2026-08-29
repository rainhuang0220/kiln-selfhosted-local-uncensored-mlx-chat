from app.services.thinking import (
    normalize_effort,
    remap_assistant_for_history,
    split_thinking,
    thinking_budget_for,
)


def test_split_think_block():
    content, reasoning = split_thinking(
        "<think>plan the answer</think>\n\nHello there."
    )
    assert reasoning == "plan the answer"
    assert content == "Hello there."


def test_split_no_think():
    content, reasoning = split_thinking("just text")
    assert content == "just text"
    assert reasoning == ""


def test_split_unclosed_think():
    content, reasoning = split_thinking("<think>still thinking")
    assert reasoning == "still thinking"
    assert content == ""


def test_thinking_budget_low_is_half_or_less_of_medium():
    low = thinking_budget_for("low")
    mid = thinking_budget_for("medium")
    high = thinking_budget_for("xhigh")
    assert low == 256
    assert mid == 1024
    assert high is None
    assert low * 2 <= mid
    assert thinking_budget_for("max") is None
    assert thinking_budget_for("mid") == 1024


def test_remap_uses_reasoning_content():
    out = remap_assistant_for_history(
        {"role": "assistant", "content": "Hi", "reasoning": "I greet"}
    )
    assert out["reasoning_content"] == "I greet"
    assert "reasoning" not in out
