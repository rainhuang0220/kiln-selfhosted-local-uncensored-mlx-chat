from app.services.sampling import (
    NON_THINKING,
    THINKING,
    mlx_repetition_penalty,
    resolve_sampling,
)


def test_thinking_uses_qwen_recommended_preset():
    got = resolve_sampling(enable_thinking=True)
    assert got["temperature"] == THINKING["temperature"]
    assert got["top_p"] == THINKING["top_p"]
    assert got["top_k"] == THINKING["top_k"]
    assert got["repetition_penalty"] == 1.0
    assert got["presence_penalty"] == 0.0


def test_non_thinking_uses_qwen_recommended_preset():
    got = resolve_sampling(enable_thinking=False)
    assert got["temperature"] == NON_THINKING["temperature"]
    assert got["top_p"] == NON_THINKING["top_p"]
    assert got["top_k"] == NON_THINKING["top_k"]


def test_explicit_override_wins():
    got = resolve_sampling(
        enable_thinking=True,
        temperature=1.0,
        top_p=0.5,
        top_k=40,
        presence_penalty=0.5,
        repetition_penalty=1.08,
        repetition_context_size=128,
    )
    assert got["temperature"] == 1.0
    assert got["top_p"] == 0.5
    assert got["top_k"] == 40
    assert got["presence_penalty"] == 0.5
    assert got["repetition_penalty"] == 1.08
    assert got["repetition_context_size"] == 128


def test_mlx_repetition_adapter_does_not_send_hf_identity_as_one():
    assert mlx_repetition_penalty(1.0) == 0.0
    assert mlx_repetition_penalty(0.0) == 0.0
    assert mlx_repetition_penalty(None) == 0.0
    assert mlx_repetition_penalty(1.08) == 1.08
