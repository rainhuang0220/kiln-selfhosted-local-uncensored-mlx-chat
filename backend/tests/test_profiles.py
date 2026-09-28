from app.services.profiles import DEFAULT_PROFILE, normalize_profile, resolve_profile


def test_interactive_dialogue_disables_thinking_and_continuation():
    profile = resolve_profile("interactive_dialogue")
    assert profile["enable_thinking"] is False
    assert profile["thinking_continuation"] is False
    assert profile["max_tokens"] <= 4096
    assert profile["max_tokens"] >= 3072
    assert profile["repetition_penalty"] == 1.0
    assert profile["prompt_soft_target"] <= 10240
    assert profile["prompt_budget"] <= 12288
    assert profile["prompt_soft_target"] < profile["prompt_budget"]


def test_immersive_budget_and_min_output():
    profile = resolve_profile("immersive")
    assert profile["profile"] == "immersive"
    assert profile["max_tokens"] >= 4096
    assert profile["min_output_chars"] >= 5000
    assert profile["target_output_chars"] >= 10000
    assert profile["auto_continue_max"] >= 1
    assert profile["presence_penalty"] <= 0.25
    # Count-scaled penalties push CJK prose into synonym chains past ~3k chars.
    assert profile["frequency_penalty"] == 0.0
    assert 1.08 <= profile["repetition_penalty"] <= 1.18
    # A paragraph cycle is ~900 tokens; the presence window has to see it.
    assert profile["presence_context_size"] >= 1024
    assert profile["enable_thinking"] is False
    assert profile.get("completion_soft_cap", 12288) <= 12288
    assert profile.get("completion_soft_cap", 12288) >= 5000


def test_long_form_and_narrative_alias_immersive():
    assert normalize_profile("narrative") == "immersive"
    assert normalize_profile("multi_scenario") == "immersive"
    long_form = resolve_profile("long_form")
    assert long_form["min_output_chars"] >= 5000
    assert long_form["target_visible_chars"] == 10000


def test_only_immersive_profiles_keep_pins():
    assert resolve_profile("immersive")["keep_pins"] is True
    assert resolve_profile("long_form")["keep_pins"] is True
    for name in ("interactive_dialogue", "balanced", "reasoning"):
        assert not resolve_profile(name).get("keep_pins"), name


def test_fast_aliases_to_interactive_dialogue():
    assert normalize_profile("fast") == "interactive_dialogue"
    profile = resolve_profile("fast")
    assert profile["profile"] == "interactive_dialogue"
    assert profile["max_tokens"] <= 4096
    assert profile.get("auto_continue_max", 0) == 0 or "auto_continue_max" not in profile


def test_reasoning_keeps_thinking_without_manual_continuation():
    profile = resolve_profile("reasoning")
    assert profile["enable_thinking"] is True
    assert profile["thinking_continuation"] is False
    assert profile["max_tokens"] >= 4096
    assert profile["prompt_budget"] >= 16384


def test_unknown_profile_falls_back_to_default():
    assert resolve_profile("not-a-real-profile")["profile"] == DEFAULT_PROFILE
    assert DEFAULT_PROFILE == "immersive"
