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
