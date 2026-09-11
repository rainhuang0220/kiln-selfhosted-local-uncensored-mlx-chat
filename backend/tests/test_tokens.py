from pathlib import Path

from app.services.tokens import TokenEstimator


def test_estimator_counts_messages():
    model = Path(__file__).resolve().parents[3] / "qwen3.8-27b"
    est = TokenEstimator(str(model))
    n = est.count_messages(
        [
            {"role": "system", "content": "You are Kiln."},
            {"role": "user", "content": "hello"},
        ]
    )
    assert n > 5
    assert est.method in {"hf_tokenizer", "chars_div_4"}


def test_continue_prefix_is_unclosed_assistant():
    est = TokenEstimator("/nonexistent-model")
    prompt = est.apply_chat_template(
        [{"role": "user", "content": "go on"}],
        assistant_prefix="partial line",
    )
    assert prompt.endswith("<|im_start|>assistant\npartial line")
    assert not prompt.endswith("<|im_end|>")
