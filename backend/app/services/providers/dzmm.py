"""DZMM provider and local wallet configuration. Never return the token to clients."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
import base64
import struct
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from app.providers.base import ChatChunk, ChatRequest, ChatResult
from app.providers.sse import iter_sse_frames

MODELS_URL = "https://api.sillytraven.dev/api/xiaoshuoai/ext/v2/models"
V2_CHAT_URL = "https://api.sillytraven.dev/api/xiaoshuoai/ext/v2/chat/completions"
V1_CHAT_URL = "https://api.sillytraven.dev/api/xiaoshuoai/ext/v1/chat/completions"
LOCAL_9B = "local:9b"
TURBO = "nalang-turbo-0826"


class DzmmQuotaError(RuntimeError):
    def __init__(self, status: int):
        super().__init__("DZMM quota exhausted")
        self.status = status


def _quota_exhausted(payload: dict[str, Any]) -> bool:
    error = payload.get("error") or {}
    if not isinstance(error, dict):
        return False
    code = str(error.get("code") or error.get("status") or "").lower()
    message = str(error.get("message") or "").lower()
    return code in {"402", "429", "insufficient_quota", "rate_limit", "quota_exceeded"} or any(
        phrase in message for phrase in ("额度用尽", "余额不足", "quota exhausted", "insufficient credits")
    )


def token_path(sqlite_path: str) -> Path:
    return Path(sqlite_path).expanduser().parent / "dzmm-settings.json"


def read_token(sqlite_path: str) -> str:
    path = token_path(sqlite_path)
    try:
        return str(json.loads(path.read_text())["api_token"]).strip()
    except (OSError, KeyError, ValueError, TypeError):
        return ""


def write_token(sqlite_path: str, token: str) -> None:
    path = token_path(sqlite_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="dzmm-settings-", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump({"api_token": token.strip()}, handle)
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def preferred_model(has_token: bool) -> str:
    return TURBO if has_token else LOCAL_9B


def model_catalog(prices: dict[str, str] | None = None, extra_ids: list[str] | None = None) -> list[dict[str, str]]:
    prices = prices or {}
    catalog = json.loads((Path(__file__).resolve().parents[2] / "data" / "dzmm_catalog.json").read_text())
    rows = [(item["id"], item["label"], item["quality"], item["speed"], item["long_card"], item["quota"])
            for item in catalog["models"]]
    for model_id in extra_ids or []:
        if model_id.startswith("nalang-apex") and model_id not in {row[0] for row in rows}:
            rows.append((model_id, "Apex · 见模型目录", "见模型目录", "见模型目录", "见模型目录", "积分"))
    return [
        {"id": mid, "label": label, "quality": quality, "speed": speed, "long_card": long_card,
         "privacy": "本机" if mid.startswith("local:") else "出网",
         "price": "电费" if mid.startswith("local:") else prices.get(mid, "见充值页"),
         "quota": quota,
        }
        for mid, label, quality, speed, long_card, quota in rows
    ]


def card_from_context(frame: dict[str, Any] | None, source_text: str = "", recall_query: str = "") -> dict[str, str]:
    frame = frame or {}
    actor = frame.get("active_character") or {}
    source = source_text or str(frame.get("source_text") or "")
    # The source can be a compiled notebook. Keep the opening role and preferences,
    # and never dump an event ledger into a character description.
    source = source.split("EVENT_LEDGER", 1)[0]
    source = source.split("小学日记", 1)[0]
    ir = frame.get("context_ir") or {}
    role = (ir.get("persona") or {}).get("role") if isinstance(ir, dict) else ""
    preferences = "；".join(str(item) for item in (frame.get("preferences") or [])[:4])
    description = "\n".join(filter(None, [
        str(actor.get("description") or role or ""),
        f"用户偏好：{preferences}" if preferences else "",
        source,
    ])).strip()[:2400]
    names = [str(person.get("name") or "") for person in ((frame.get("references") or {}).get("people") or [])]
    matches = [name for name in names if name and name in recall_query]
    if matches:
        events = (frame.get("references") or {}).get("events") or []
        notes = [str(event.get("gist") or "") for event in events
                 if any(name in (event.get("who") or []) for name in matches)]
        if notes:
            description += "\n相关记忆：" + "；".join(notes)[:800]
    return {
        "name": str(actor.get("name") or "技师"),
        "description": description,
        "scenario": str(frame.get("active_scene") or frame.get("current_scene") or actor.get("scenario") or "")[:800],
        "personality": str(actor.get("personality") or "")[:200],
        "first_mes": str(actor.get("first_mes") or "")[:300],
    }


def parse_character_card(raw: bytes, filename: str) -> dict[str, Any]:
    """Read Tavern V2/V3 JSON or PNG metadata without image dependencies."""
    if len(raw) > 8_000_000:
        raise ValueError("character card too large")
    if filename.lower().endswith(".png"):
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("invalid PNG")
        offset = 8
        metadata = None
        while offset + 12 <= len(raw):
            length = struct.unpack_from(">I", raw, offset)[0]
            if length > 8_000_000 or offset + 12 + length > len(raw):
                raise ValueError("invalid PNG chunk")
            kind = raw[offset + 4:offset + 8]
            chunk = raw[offset + 8:offset + 8 + length]
            offset += length + 12
            if kind == b"tEXt":
                key, sep, value = chunk.partition(b"\0")
                if sep and key in {b"chara", b"ccv3"}:
                    metadata = base64.b64decode(value, validate=True)
                    break
        if metadata is None:
            raise ValueError("PNG has no Tavern card metadata")
        raw = metadata
    elif not filename.lower().endswith(".json"):
        raise ValueError("import a JSON or PNG character card")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("invalid character card JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid character card")
    data = payload.get("data") or payload
    if not isinstance(data, dict):
        raise ValueError("invalid character card data")
    card = {key: str(data.get(key) or "") for key in
            ("name", "description", "personality", "scenario", "first_mes", "mes_example")}
    tags = data.get("tags") or []
    if isinstance(tags, list):
        card["tags"] = [str(tag)[:60] for tag in tags[:24] if isinstance(tag, str)]
    if not card["name"]:
        raise ValueError("character card needs a name")
    return card


class DzmmProvider:
    name = "dzmm"

    def __init__(self, token: str, model: str = TURBO, client: httpx.AsyncClient | None = None):
        if not token:
            raise ValueError("DZMM Token required")
        if not model.startswith("nalang-"):
            raise ValueError("unsupported DZMM model")
        self.token = token
        self.model = model
        self._client = client

    def context_window(self) -> int:
        return 32768

    def default_model(self) -> str:
        return self.model

    async def health(self) -> bool:
        return True

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=5.0), trust_env=False)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _payload(self, request: ChatRequest, stream: bool) -> dict[str, Any]:
        messages = [dict(m) for m in request.messages if m.get("role") in {"user", "assistant"}][-33:]
        card = request.extra.get("dzmm_card") if request.extra else None
        if not card:
            system = next((m.get("content") for m in request.messages if m.get("role") == "system"), "")
            if system:
                messages.insert(0, {"role": "system", "content": str(system)[:2500]})
        body: dict[str, Any] = {
            "model": self.model, "messages": messages, "stream": stream,
            "max_tokens": request.max_tokens, "temperature": request.temperature,
            "top_p": request.top_p, "enable_thinking": False,
        }
        if card:
            body["card"] = card
        return body

    async def _response(self, request: ChatRequest, stream: bool):
        client = await self._get_client()
        headers = {"Authorization": f"Bearer {self.token}"}
        body = self._payload(request, stream)
        # Probe v2 with card fields first. A provider lacking them can still use v1.
        for url in (V2_CHAT_URL, V1_CHAT_URL):
            payload = body
            if url == V1_CHAT_URL:
                payload = dict(body)
                card = payload.pop("card", None)
                if card:
                    system = "\n".join(f"{k}: {v}" for k, v in card.items() if v)[:2500]
                    payload["messages"] = [{"role": "system", "content": system}, *payload["messages"]]
            response = await client.send(client.build_request("POST", url, headers=headers, json=payload), stream=stream)
            if response.status_code in (404, 422) and url == V2_CHAT_URL:
                await response.aclose()
                continue
            if response.status_code in (402, 429):
                status = response.status_code
                await response.aclose()
                raise DzmmQuotaError(status)
            if response.status_code >= 400:
                status = response.status_code
                if status == 400:
                    try:
                        await response.aread()
                        if _quota_exhausted(response.json()):
                            await response.aclose()
                            raise DzmmQuotaError(status)
                    except (ValueError, TypeError):
                        pass
                await response.aclose()
                raise RuntimeError(f"DZMM request failed ({status})")
            return response
        raise RuntimeError("DZMM chat endpoint unavailable")

    async def complete(self, request: ChatRequest) -> ChatResult:
        response = await self._response(request, False)
        try:
            data = response.json()
        finally:
            await response.aclose()
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage") or {}
        return ChatResult(
            id=str(data.get("id") or uuid.uuid4()), model=self.model,
            content=str((choice.get("message") or {}).get("content") or ""), reasoning="",
            finish_reason=choice.get("finish_reason"),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            cached_tokens=0, usage_source="upstream" if usage else "estimated",
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        response = await self._response(request, True)
        rid = str(uuid.uuid4())
        try:
            async for frame in iter_sse_frames(response.aiter_text()):
                if frame.kind == "done":
                    yield ChatChunk(id=rid, model=self.model, wire_done=True)
                    return
                if frame.kind == "keepalive":
                    yield ChatChunk(id=rid, model=self.model, keepalive=frame.raw)
                    continue
                if frame.kind != "json" or frame.payload is None:
                    continue
                data = frame.payload
                if _quota_exhausted(data):
                    raise DzmmQuotaError(402)
                choice = (data.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                usage = data.get("usage") or {}
                yield ChatChunk(
                    id=str(data.get("id") or rid), model=self.model,
                    delta_content=delta.get("content"), finish_reason=choice.get("finish_reason"),
                    prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
                )
            yield ChatChunk(id=rid, model=self.model, http_eof=True)
        finally:
            await response.aclose()
