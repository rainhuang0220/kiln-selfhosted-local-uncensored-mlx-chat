from app.services.profiles import DEFAULT_PROFILE, resolve_profile


def test_interactive_dialogue_disables_thinking_and_continuation():
    profile = resolve_profile("interactive_dialogue")
    assert profile["enable_thinking"] is False
    assert profile["thinking_continuation"] is False
    assert profile["max_tokens"] <= 2048
    assert profile["repetition_penalty"] == 1.0


def test_reasoning_keeps_thinking_without_manual_continuation():
    profile = resolve_profile("reasoning")
    assert profile["enable_thinking"] is True
    assert profile["thinking_continuation"] is False
    assert profile["max_tokens"] >= 4096


def test_unknown_profile_falls_back_to_default():
    assert resolve_profile("not-a-real-profile")["profile"] == DEFAULT_PROFILE
