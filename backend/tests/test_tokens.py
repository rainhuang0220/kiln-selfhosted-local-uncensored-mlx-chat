from pathlib import Path

import pytest

from app.services.tokens import TokenEstimator


def test_count_messages_survives_missing_model_dir():
    est = TokenEstimator("/definitely-not-a-model")
    n = est.count_messages([{"role": "user", "content": "hello"}])
    assert n >= 1


def test_estimator_counts_messages():
    model = Path(__file__).resolve().parents[3] / "qwen3.8-27b"
    if not (model / "tokenizer.json").exists():
        pytest.skip("local model tokenizer not present")
    est = TokenEstimator(str(model))
    n = est.count_messages(
        [
            {"role": "system", "content": "You are Kiln."},
            {"role": "user", "content": "hello"},
        ]
    )
    assert n > 5
    assert est.method in {"hf_chat_template", "hf_tokenizer", "chars_div_4"}


def test_continue_prefix_is_unclosed_assistant():
    model = Path("/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4")
    if not (model / "chat_template.jinja").exists():
        return
    est = TokenEstimator(str(model))
    prompt = est.apply_chat_template(
        [
            {"role": "user", "content": "go on"},
            {"role": "assistant", "content": "partial line"},
        ],
        continue_final_message=True,
        add_generation_prompt=False,
        enable_thinking=False,
    )
    assert prompt.endswith("partial line")
    assert not prompt.endswith("<|im_end|>")
