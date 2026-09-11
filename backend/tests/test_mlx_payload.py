from app.config import Settings
from app.providers.base import ChatRequest
from app.providers.mlx import MlxProvider
from app.services.sampling import mlx_repetition_penalty


def test_mlx_payload_includes_supported_sampling_fields():
    provider = MlxProvider(Settings(mlx_base_url="http://127.0.0.1:8081"))
    req = ChatRequest(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.7,
        top_p=0.8,
        top_k=20,
        min_p=0.0,
        presence_penalty=0.5,
        presence_context_size=256,
        frequency_penalty=0.0,
        frequency_context_size=256,
        repetition_penalty=1.08,
        repetition_context_size=128,
        enable_thinking=False,
    )
    body = provider._payload(req, True)
    assert body["temperature"] == 0.7
    assert body["top_p"] == 0.8
    assert body["top_k"] == 20
    assert body["min_p"] == 0.0
    assert body["presence_penalty"] == 0.5
    assert body["presence_context_size"] == 256
    assert body["frequency_penalty"] == 0.0
    assert body["repetition_penalty"] == mlx_repetition_penalty(1.08) == 1.08
    assert body["repetition_context_size"] == 128
    assert body["chat_template_kwargs"]["enable_thinking"] is False
    assert body["stream_options"] == {"include_usage": True}


def test_hf_identity_repetition_is_normalized_for_mlx():
    provider = MlxProvider(Settings(mlx_base_url="http://127.0.0.1:8081"))
    req = ChatRequest(messages=[{"role": "user", "content": "hi"}], repetition_penalty=1.0)
    assert provider._payload(req, False)["repetition_penalty"] == 0.0


def test_continue_prefix_uses_completions_not_chat(monkeypatch):
    provider = MlxProvider(Settings(mlx_base_url="http://127.0.0.1:8081"))
    captured: dict = {}

    async def fake_stream_post(url, body):
        captured["url"] = url
        captured["body"] = body
        if False:
            yield {}

    monkeypatch.setattr(provider, "_stream_post", fake_stream_post)
    req = ChatRequest(
        messages=[{"role": "user", "content": "hi"}],
        extra={"raw_prompt": "<|im_start|>user\nhi<|im_end|>\n<|im_start|>assistant\npartial"},
    )

    async def run():
        return [chunk async for chunk in provider.stream(req)]

    import asyncio

    asyncio.run(run())
    assert captured["url"].endswith("/completions")
    assert captured["body"]["prompt"].endswith("partial")
    assert "messages" not in captured["body"]
