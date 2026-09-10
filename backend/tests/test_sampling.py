from app.services.sampling import NON_THINKING, THINKING, resolve_sampling


def test_thinking_uses_qwen_recommended_preset():
    got = resolve_sampling(enable_thinking=True)
    assert got == THINKING
    assert got == {"temperature": 0.6, "top_p": 0.95, "top_k": 20}


def test_non_thinking_uses_qwen_recommended_preset():
    got = resolve_sampling(enable_thinking=False)
    assert got == NON_THINKING
    assert got == {"temperature": 0.7, "top_p": 0.8, "top_k": 20}


def test_explicit_override_wins():
    got = resolve_sampling(enable_thinking=True, temperature=1.0, top_p=0.5, top_k=40)
    assert got == {"temperature": 1.0, "top_p": 0.5, "top_k": 40}
