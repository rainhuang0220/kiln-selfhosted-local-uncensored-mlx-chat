from hashlib import sha256
from pathlib import Path

import pytest

from app.services.tokens import TokenEstimator

MODEL = Path("/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4")
TEMPLATE_SHA256 = "d190fb2a6f405f80bbfd437ad631ef6faee914d8601463aa6be0ddcdee8468c6"

CASES = [
    (
        "zh",
        [{"role": "user", "content": "继续"}, {"role": "assistant", "content": "雨停了，钥匙还在"}],
        False,
    ),
    (
        "punct",
        [{"role": "user", "content": "go"}, {"role": "assistant", "content": "Wait—"}],
        False,
    ),
    (
        "md",
        [{"role": "user", "content": "code"}, {"role": "assistant", "content": '```python\nprint("hi")'}],
        False,
    ),
    (
        "quotes",
        [{"role": "user", "content": "say"}, {"role": "assistant", "content": "他说“还在”"}],
        False,
    ),
    (
        "unicode",
        [{"role": "user", "content": "emoji"}, {"role": "assistant", "content": "灯还亮着 🙂"}],
        False,
    ),
    (
        "newline",
        [{"role": "user", "content": "n"}, {"role": "assistant", "content": "第一行\n"}],
        False,
    ),
    (
        "mid_think",
        [{"role": "user", "content": "why"}, {"role": "assistant", "content": "<think>\nhalf plan\n"}],
        True,
    ),
]


def _require_model() -> Path:
    if not (MODEL / "chat_template.jinja").exists() or not (MODEL / "tokenizer.json").exists():
        pytest.skip(f"model tokenizer not present: {MODEL}")
    return MODEL


def _native(messages: list[dict], enable_thinking: bool) -> str:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(MODEL), trust_remote_code=True)
    return tok.apply_chat_template(
        messages,
        tokenize=False,
        continue_final_message=True,
        add_generation_prompt=False,
        enable_thinking=enable_thinking,
    )


@pytest.mark.parametrize("name,messages,thinking", CASES, ids=[c[0] for c in CASES])
def test_continue_matches_tokenizer_native(name, messages, thinking):
    _require_model()
    est = TokenEstimator(str(MODEL))
    got = est.apply_chat_template(
        messages,
        continue_final_message=True,
        add_generation_prompt=False,
        enable_thinking=thinking,
    )
    expected = _native(messages, thinking)
    assert got == expected
    assert "<|im_start|>user\ncontinue" not in got
    assert not got.endswith("<|im_end|>")
    if name == "mid_think":
        assert got.rstrip().endswith("half plan")
        assert not got.rstrip().endswith("</think>")


def test_chat_template_revision_is_pinned():
    _require_model()
    digest = sha256((MODEL / "chat_template.jinja").read_bytes()).hexdigest()
    assert digest == TEMPLATE_SHA256


def test_native_continue_rejects_generation_prompt():
    _require_model()
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(MODEL), trust_remote_code=True)
    with pytest.raises(ValueError, match="continue_final_message"):
        tok.apply_chat_template(
            [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "pa"}],
            tokenize=False,
            add_generation_prompt=True,
            continue_final_message=True,
            enable_thinking=False,
        )


def test_think_cut_prompt_drops_last_native_token():
    _require_model()
    from transformers import AutoTokenizer

    from app.config import Settings
    from app.providers.base import ChatRequest
    from app.providers.mlx import MlxProvider

    tok = AutoTokenizer.from_pretrained(str(MODEL), trust_remote_code=True)
    messages = [{"role": "user", "content": "why"}]
    expected = tok.apply_chat_template(
        [
            *messages,
            {"role": "assistant", "content": "", "reasoning_content": "half plan"},
        ],
        tokenize=False,
        continue_final_message=True,
        add_generation_prompt=False,
        enable_thinking=True,
    )
    provider = MlxProvider(Settings(mlx_base_url="http://127.0.0.1:8081", model_path=str(MODEL)))
    got, tail = provider._continuation_prompt(
        ChatRequest(messages=messages, extra={}),
        "half plan",
    )
    ids = tok.encode(expected, add_special_tokens=False)
    assert got != expected
    assert tok.encode(got, add_special_tokens=False) == ids[:-1]
    assert tail == tok.decode([ids[-1]], skip_special_tokens=False)
    assert "<|im_start|>user\ncontinue" not in got
    assert "</think>" in got or "</think>" in tail


def test_completion_prompt_avoids_used_prefix():
    _require_model()
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(MODEL), trust_remote_code=True)
    messages = [
        {"role": "user", "content": "继续"},
        {"role": "assistant", "content": "雨停了，钥匙还在"},
    ]
    est = TokenEstimator(str(MODEL))
    first, _ = est.continuation_completion_prompt(messages, enable_thinking=False)
    second, _ = est.continuation_completion_prompt(
        messages, enable_thinking=False, used_prompts=[first]
    )
    native = _native(messages, False)
    ids = tok.encode(native, add_special_tokens=False)
    assert first != second
    assert tok.encode(first, add_special_tokens=False) == ids[:-1]
    assert tok.encode(second, add_special_tokens=False) == ids[:-2]


def test_mid_think_uses_official_generation_prefix():
    _require_model()
    est = TokenEstimator(str(MODEL))
    messages = [{"role": "user", "content": "why"}]
    prefix = est.apply_chat_template(
        messages,
        add_generation_prompt=True,
        enable_thinking=True,
    )
    prompt, tail = est.mid_think_completion_prompt(messages, "half plan")
    assert prefix.endswith("<think>\n") or "<think>" in prefix
    assert (prompt + tail).startswith(prefix)
    assert "half plan" in prompt + tail
    assert not prompt.rstrip().endswith("</think>")
    assert "<|im_start|>user\ncontinue" not in prompt


def test_completion_prompt_drops_last_native_token():
    _require_model()
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(MODEL), trust_remote_code=True)
    messages = [
        {"role": "user", "content": "继续"},
        {"role": "assistant", "content": "雨停了，钥匙还在"},
    ]
    est = TokenEstimator(str(MODEL))
    prompt, tail = est.continuation_completion_prompt(messages, enable_thinking=False)
    native = _native(messages, False)
    ids = tok.encode(native, add_special_tokens=False)
    assert tail == tok.decode([ids[-1]], skip_special_tokens=False)
    assert tok.encode(prompt, add_special_tokens=False) == ids[:-1]
    assert not prompt.endswith("<|im_end|>")
    assert "<|im_start|>user\ncontinue" not in prompt
