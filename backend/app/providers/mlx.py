from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import httpx

from app.config import Settings, settings as default_settings
from app.providers.base import ChatChunk, ChatRequest, ChatResult
from app.services.thinking import split_thinking


ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "host.docker.internal"}


def _assert_allowlisted(url: str) -> None:
    host = urlparse(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"mlx host not allowlisted: {host}")


class MlxProvider:
    name = "mlx"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or default_settings
        _assert_allowlisted(self.settings.mlx_base_url)
        self._client = client
        self._owns_client = client is None

    def context_window(self) -> int:
        return self.settings.context_window

    def default_model(self) -> str:
        return self.settings.model_name

    async def _client_obj(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    self.settings.mlx_timeout_s,
                    connect=self.settings.mlx_connect_timeout_s,
                ),
                follow_redirects=False,
            )
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def health(self) -> bool:
        client = await self._client_obj()
        try:
            resp = await client.get(self.settings.mlx_health_url())
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def _payload(self, request: ChatRequest, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": "default_model",
            "messages": request.messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "top_k": request.top_k,
            "max_tokens": request.max_tokens,
            "stream": stream,
            "chat_template_kwargs": {
                "enable_thinking": request.enable_thinking,
                "reasoning_effort": request.reasoning_effort,
                "preserve_thinking": request.preserve_thinking,
            },
        }
        if stream:
            body["stream_options"] = {"include_usage": True}
        if request.stop:
            body["stop"] = request.stop
        if request.tools:
            body["tools"] = request.tools
        return body

    def _continuation_prompt(self, request: ChatRequest, reasoning: str) -> str:
        parts: list[str] = []
        for msg in request.messages:
            role = msg.get("role") or "user"
            content = msg.get("content") or ""
            thought = msg.get("reasoning_content") or msg.get("reasoning") or ""
            body = f"<think>\n{thought}\n</think>\n\n{content}" if role == "assistant" and thought else content
            parts.append(f"<|im_start|>{role}\n{body}<|im_end|>\n")
        return (
            "".join(parts)
            + "<|im_start|>assistant\n<think>\n"
            + (reasoning or "").strip()
            + "\n</think>\n\n"
        )

    def _usage(self, data: dict[str, Any]) -> tuple[int, int, int, str]:
        usage = data.get("usage") or {}
        if not usage:
            return 0, 0, 0, "estimated"
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        details = usage.get("prompt_tokens_details") or {}
        cached = int(details.get("cached_tokens") or 0)
        return prompt, completion, cached, "upstream"

    async def complete(self, request: ChatRequest) -> ChatResult:
        client = await self._client_obj()
        try:
            resp = await client.post(self.settings.mlx_chat_url(), json=self._payload(request, False))
        except httpx.TimeoutException as exc:
            raise TimeoutError("mlx timeout") from exc
        except httpx.HTTPError as exc:
            raise ConnectionError(f"mlx unreachable: {exc}") from exc
        if resp.status_code >= 400:
            raise RuntimeError(f"mlx error {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
        if not reasoning and content:
            content, reasoning = split_thinking(content)
        prompt, completion, cached, source = self._usage(data)
        return ChatResult(
            id=data.get("id") or f"chatcmpl-{uuid.uuid4()}",
            model=self.default_model(),
            content=content or "",
            reasoning=reasoning or "",
            finish_reason=choice.get("finish_reason") or "stop",
            prompt_tokens=prompt,
            completion_tokens=completion,
            cached_tokens=cached,
            usage_source=source,
            raw=data,
        )

    async def _stream_post(self, url: str, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        client = await self._client_obj()
        try:
            async with client.stream("POST", url, json=body) as resp:
                if resp.status_code >= 400:
                    err = (await resp.aread()).decode("utf-8", errors="replace")
                    raise RuntimeError(f"mlx error {resp.status_code}: {err[:400]}")
                buffer = ""
                async for raw in resp.aiter_text():
                    buffer += raw
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip("\r")
                        if not line:
                            continue
                        if line.startswith(":"):
                            yield {"keepalive": line[1:].strip()}
                            continue
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            return
                        try:
                            yield json.loads(payload)
                        except json.JSONDecodeError:
                            continue
        except httpx.TimeoutException as exc:
            raise TimeoutError("mlx timeout") from exc
        except httpx.HTTPError as exc:
            raise ConnectionError(f"mlx unreachable: {exc}") from exc

    def _chunk_from_event(self, data: dict[str, Any], req_id: str, model: str) -> ChatChunk:
        prompt, completion, cached, _ = self._usage(data)
        if data.get("keepalive") is not None:
            return ChatChunk(id=req_id, model=model, keepalive=str(data["keepalive"]))
        req_id = data.get("id") or req_id
        choices = data.get("choices") or []
        if not choices:
            return ChatChunk(
                id=req_id,
                model=model,
                prompt_tokens=prompt or None,
                completion_tokens=completion or None,
                cached_tokens=cached or None,
            )
        choice = choices[0]
        delta = choice.get("delta") or choice.get("message") or {}
        text = choice.get("text") or delta.get("content")
        return ChatChunk(
            id=req_id,
            model=model,
            delta_content=text,
            delta_reasoning=delta.get("reasoning") or delta.get("reasoning_content"),
            finish_reason=choice.get("finish_reason"),
            prompt_tokens=prompt or None,
            completion_tokens=completion or None,
            cached_tokens=cached or None,
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        req_id = f"chatcmpl-{uuid.uuid4()}"
        model = self.default_model()
        async for data in self._stream_post(self.settings.mlx_chat_url(), self._payload(request, True)):
            yield self._chunk_from_event(data, req_id, model)

    async def complete_after_think(
        self, request: ChatRequest, reasoning: str, max_tokens: int
    ) -> ChatResult:
        client = await self._client_obj()
        body: dict[str, Any] = {
            "model": "default_model",
            "prompt": self._continuation_prompt(request, reasoning),
            "max_tokens": max(1, max_tokens),
            "temperature": request.temperature,
            "top_p": request.top_p,
            "top_k": request.top_k,
            "stream": False,
        }
        try:
            resp = await client.post(self.settings.mlx_completions_url(), json=body)
        except httpx.TimeoutException as exc:
            raise TimeoutError("mlx timeout") from exc
        except httpx.HTTPError as exc:
            raise ConnectionError(f"mlx unreachable: {exc}") from exc
        if resp.status_code >= 400:
            raise RuntimeError(f"mlx error {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        text = choice.get("text") or ""
        prompt, completion, cached, source = self._usage(data)
        return ChatResult(
            id=data.get("id") or f"chatcmpl-{uuid.uuid4()}",
            model=self.default_model(),
            content=text,
            reasoning="",
            finish_reason=choice.get("finish_reason") or "stop",
            prompt_tokens=prompt,
            completion_tokens=completion,
            cached_tokens=cached,
            usage_source=source,
            raw=data,
        )

    async def stream_after_think(
        self, request: ChatRequest, reasoning: str, max_tokens: int
    ) -> AsyncIterator[ChatChunk]:
        req_id = f"chatcmpl-{uuid.uuid4()}"
        model = self.default_model()
        body: dict[str, Any] = {
            "model": "default_model",
            "prompt": self._continuation_prompt(request, reasoning),
            "max_tokens": max(1, max_tokens),
            "temperature": request.temperature,
            "top_p": request.top_p,
            "top_k": request.top_k,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        async for data in self._stream_post(self.settings.mlx_completions_url(), body):
            chunk = self._chunk_from_event(data, req_id, model)
            if chunk.delta_reasoning and not chunk.delta_content:
                chunk = ChatChunk(
                    id=chunk.id,
                    model=chunk.model,
                    delta_content=chunk.delta_reasoning,
                    finish_reason=chunk.finish_reason,
                    prompt_tokens=chunk.prompt_tokens,
                    completion_tokens=chunk.completion_tokens,
                    cached_tokens=chunk.cached_tokens,
                )
            yield chunk
