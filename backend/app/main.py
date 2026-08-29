from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.auth import AuthRateMiddleware
from app.config import Settings, settings as default_settings
from app.db import init_db
from app.errors import error_body, install_error_handlers
from app.providers.mlx import MlxProvider
from app.services import accounts
from app.services.chat import ChatService
from app.services.memory import MemoryService
from app.services.tokens import TokenEstimator


class ChatBody(BaseModel):
    message: str = ""
    conversation_id: str | None = None
    regenerate: bool = False
    system: str | None = None
    stream: bool = True
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_tokens: int | None = None
    enable_thinking: bool | None = None
    reasoning_effort: str | None = None


class RenameBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class MemoryBody(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    memory_type: str = "fact"
    key: str | None = None
    importance: float = 0.5


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class RegisterBody(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class OpenAIChatBody(BaseModel):
    model: str | None = None
    messages: list[dict[str, Any]]
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_tokens: int | None = None
    stream: bool = False
    stream_options: dict[str, Any] | None = None
    conversation_id: str | None = None
    store: bool = False
    enable_thinking: bool | None = None
    tools: list[dict[str, Any]] | None = None


def _sse(event: str, data: Any) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    if event == "data":
        return f"data: {payload}\n\n".encode("utf-8")
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def create_app(settings: Settings | None = None, chat: ChatService | None = None) -> FastAPI:
    cfg = settings or default_settings

    def _owner(request: Request) -> str | None:
        return getattr(request.state, "user_id", None)

    def _session_cookie(resp: JSONResponse, token: str) -> JSONResponse:
        resp.set_cookie(
            accounts.COOKIE,
            token,
            httponly=True,
            samesite="lax",
            secure=bool(cfg.cookie_secure),
            max_age=max(1, cfg.session_days) * 24 * 3600,
            path="/",
        )
        return resp

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(cfg.sqlite_path)
        if cfg.bootstrap_username and cfg.bootstrap_password:
            try:
                accounts.ensure_bootstrap(cfg.bootstrap_username, cfg.bootstrap_password)
            except ValueError:
                pass
        if chat is None:
            provider = MlxProvider(cfg)
            tokenizer = TokenEstimator(cfg.model_path)
            app.state.provider = provider
            app.state.chat = ChatService(cfg, provider, tokenizer, MemoryService())
        else:
            app.state.chat = chat
            app.state.provider = getattr(chat, "provider", None)
        app.state.settings = cfg
        try:
            yield
        finally:
            provider = getattr(app.state, "provider", None)
            if provider is not None and hasattr(provider, "aclose"):
                await provider.aclose()

    gated = bool(cfg.bootstrap_username or cfg.bootstrap_password)
    docs = None if gated else "/docs"
    app = FastAPI(
        title="Kiln",
        version="0.3.0",
        lifespan=lifespan,
        docs_url=docs,
        redoc_url=None if gated else "/redoc",
        openapi_url=None if gated else "/openapi.json",
    )
    install_error_handlers(app)
    app.add_middleware(
        AuthRateMiddleware,
        chat_per_minute=cfg.chat_per_minute,
        login_per_minute=cfg.login_per_minute,
        max_request_bytes=cfg.max_request_bytes,
        trust_proxy_headers=cfg.trust_proxy_headers,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health")
    async def health(request: Request):
        provider = getattr(request.app.state, "provider", None)
        reachable = False
        if provider is not None:
            reachable = await provider.health()
        base = "" if accounts.user_count() else cfg.mlx_base_url
        return {
            "status": "ok",
            "provider": {
                "name": getattr(provider, "name", "mlx"),
                "reachable": reachable,
                "base_url": base,
            },
            "model": cfg.model_name,
            "context_window": cfg.context_window,
            "practical_prompt_budget": cfg.practical_prompt_budget,
            "default_max_tokens": cfg.default_max_tokens,
            "max_tokens_cap": cfg.max_tokens_cap,
            "enable_thinking": cfg.enable_thinking,
        }

    @app.get("/auth/status")
    async def auth_status(request: Request):
        n = accounts.user_count()
        required = n > 0
        user = getattr(request.state, "user", None)
        return {
            "required": required,
            "ok": (not required) or user is not None,
            "setup": n == 0,
            "signup": bool(cfg.auth_signup) or n == 0,
            "username": user.username if user else None,
        }

    @app.post("/auth/register")
    async def auth_register(body: RegisterBody):
        n = accounts.user_count()
        if n > 0 and not cfg.auth_signup:
            return error_body(
                "signup disabled",
                "authentication_error",
                "signup_disabled",
                status=403,
            )
        try:
            user = accounts.create_user(body.username, body.password)
        except ValueError as exc:
            return error_body(str(exc), "invalid_request_error", "invalid_body", status=400)
        except sqlite3.IntegrityError:
            return error_body(
                "username taken",
                "invalid_request_error",
                "username_taken",
                status=409,
            )
        token = accounts.create_session(user.id, days=cfg.session_days)
        resp = JSONResponse(
            {"ok": True, "required": True, "username": user.username, "setup": False}
        )
        return _session_cookie(resp, token)

    @app.post("/auth/login")
    async def auth_login(body: LoginBody):
        if accounts.user_count() == 0:
            return {"ok": True, "required": False}
        user = accounts.authenticate(body.username, body.password)
        if user is None:
            return error_body(
                "invalid username or password",
                "authentication_error",
                "auth_failed",
                status=401,
            )
        token = accounts.create_session(user.id, days=cfg.session_days)
        resp = JSONResponse({"ok": True, "required": True, "username": user.username})
        return _session_cookie(resp, token)

    @app.post("/auth/logout")
    async def auth_logout(request: Request):
        accounts.revoke_session(request.cookies.get(accounts.COOKIE))
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(accounts.COOKIE, path="/")
        return resp

    @app.get("/context")
    async def global_context(request: Request):
        return request.app.state.chat.global_context()

    @app.get("/memory")
    async def list_memories(
        request: Request,
        q: str = Query(""),
        limit: int = Query(20, ge=1, le=100),
    ):
        recs = request.app.state.chat.memory.search(q, limit=limit)
        return {
            "object": "list",
            "data": [
                {
                    "id": r.id,
                    "type": r.memory_type,
                    "key": r.key,
                    "content": r.content,
                    "importance": r.importance,
                }
                for r in recs
            ],
        }

    @app.post("/memory")
    async def create_memory(body: MemoryBody, request: Request):
        from app.services.memory_provider import MemoryRecord

        rec = request.app.state.chat.memory.save(
            MemoryRecord(
                id="",
                memory_type=body.memory_type,
                key=body.key,
                content=body.content,
                importance=body.importance,
            )
        )
        return {"id": rec.id, "content": rec.content}

    @app.post("/chat")
    async def chat_endpoint(body: ChatBody, request: Request):
        svc: ChatService = request.app.state.chat

        async def event_stream() -> AsyncIterator[bytes]:
            agen = svc.chat(
                message=body.message,
                conversation_id=body.conversation_id,
                stream=True,
                regenerate=body.regenerate,
                system=body.system,
                temperature=body.temperature,
                top_p=body.top_p,
                top_k=body.top_k,
                max_tokens=body.max_tokens,
                enable_thinking=body.enable_thinking,
                reasoning_effort=body.reasoning_effort,
                owner_id=_owner(request),
            )
            try:
                async for event in agen:
                    if await request.is_disconnected():
                        await agen.aclose()
                        return
                    yield _sse(event["event"], event["data"])
                yield b"data: [DONE]\n\n"
            except (asyncio.CancelledError, GeneratorExit):
                await agen.aclose()
                raise
            except Exception as exc:  # noqa: BLE001
                yield _sse(
                    "error",
                    {
                        "error": {
                            "message": str(exc),
                            "type": "api_error",
                            "code": "upstream_error",
                        }
                    },
                )
                yield b"data: [DONE]\n\n"

        if body.stream:
            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        meta = None
        snapshot = None
        done = None
        err = None
        async for event in svc.chat(
            message=body.message,
            conversation_id=body.conversation_id,
            stream=False,
            regenerate=body.regenerate,
            system=body.system,
            temperature=body.temperature,
            top_p=body.top_p,
            top_k=body.top_k,
            max_tokens=body.max_tokens,
            enable_thinking=body.enable_thinking,
            reasoning_effort=body.reasoning_effort,
            owner_id=_owner(request),
        ):
            name = event["event"]
            if name == "meta":
                meta = event["data"]
            elif name == "snapshot":
                snapshot = event["data"]
            elif name == "done":
                done = event["data"]
            elif name == "error":
                err = event
        if err:
            status = err.get("status") or 502
            return JSONResponse(err["data"], status_code=status)
        if not meta or not done:
            return error_body("empty generation", "api_error", "upstream_error", status=502)
        return {
            "conversation_id": meta["conversation_id"],
            "created": meta["created"],
            "message": done["message"],
            "finish_reason": done["finish_reason"],
            "model": meta["model"],
            "usage": done["usage"],
            "context": snapshot,
        }

    @app.get("/conversation")
    async def list_conversations(
        request: Request,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        q: str | None = Query(None),
    ):
        return request.app.state.chat.list_conversations(
            limit=limit, offset=offset, q=q, owner_id=_owner(request)
        )

    @app.get("/conversation/{conversation_id}")
    async def get_conversation(conversation_id: str, request: Request):
        data = request.app.state.chat.get_conversation(
            conversation_id, owner_id=_owner(request)
        )
        if data is None:
            return error_body(
                "conversation not found",
                "not_found_error",
                "conversation_not_found",
                status=404,
            )
        return data

    @app.get("/conversation/{conversation_id}/context")
    async def get_conversation_context(conversation_id: str, request: Request):
        data = request.app.state.chat.get_context(
            conversation_id, owner_id=_owner(request)
        )
        if data is None:
            return error_body(
                "conversation not found",
                "not_found_error",
                "conversation_not_found",
                status=404,
            )
        return data

    @app.delete("/conversation/{conversation_id}")
    async def delete_conversation(conversation_id: str, request: Request):
        ok = request.app.state.chat.delete_conversation(
            conversation_id, owner_id=_owner(request)
        )
        if not ok:
            return error_body(
                "conversation not found",
                "not_found_error",
                "conversation_not_found",
                status=404,
            )
        from fastapi import Response

        return Response(status_code=204)

    @app.patch("/conversation/{conversation_id}")
    async def rename_conversation(conversation_id: str, body: RenameBody, request: Request):
        ok = request.app.state.chat.rename_conversation(
            conversation_id, body.title, owner_id=_owner(request)
        )
        if not ok:
            return error_body(
                "conversation not found",
                "not_found_error",
                "conversation_not_found",
                status=404,
            )
        return {"id": conversation_id, "title": body.title}

    @app.get("/v1/models")
    async def list_models():
        return {
            "object": "list",
            "data": [
                {
                    "id": cfg.model_name,
                    "object": "model",
                    "owned_by": "local",
                }
            ],
        }

    @app.post("/v1/chat/completions")
    async def openai_chat(body: OpenAIChatBody, request: Request):
        svc: ChatService = request.app.state.chat
        messages = body.messages or []
        if not messages:
            return error_body("messages is required", "invalid_request_error", "invalid_body", param="messages")
        last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        if last_user is None:
            return error_body("need a user message", "invalid_request_error", "invalid_body", param="messages")
        system = next((m.get("content") for m in messages if m.get("role") == "system"), None)
        user_text = last_user.get("content") or ""
        if isinstance(user_text, list):
            user_text = "".join(
                part.get("text", "") for part in user_text if isinstance(part, dict)
            )
        store = body.store or bool(body.conversation_id)
        if not store:
            from app.providers.base import ChatRequest
            from app.services.thinking import normalize_effort, remap_assistant_for_history

            mapped = [
                remap_assistant_for_history(m) if m.get("role") == "assistant" else m
                for m in messages
            ]
            max_out = body.max_tokens if body.max_tokens is not None else cfg.default_max_tokens
            max_out = min(int(max_out), cfg.max_tokens_cap)
            req = ChatRequest(
                messages=mapped,
                temperature=body.temperature if body.temperature is not None else cfg.default_temperature,
                top_p=body.top_p if body.top_p is not None else cfg.default_top_p,
                top_k=body.top_k if body.top_k is not None else cfg.default_top_k,
                max_tokens=max_out,
                enable_thinking=cfg.enable_thinking if body.enable_thinking is None else body.enable_thinking,
                reasoning_effort=normalize_effort(cfg.reasoning_effort),
                tools=body.tools,
            )
            provider = request.app.state.provider
            if svc._lock.locked() or svc._busy:
                return error_body(
                    "model is busy",
                    "conflict_error",
                    "generation_in_progress",
                    status=409,
                )
            if body.stream:
                async def oai_stream() -> AsyncIterator[bytes]:
                    async with svc._lock:
                        async for chunk in provider.stream(req):
                            delta: dict[str, Any] = {"role": "assistant"}
                            if chunk.delta_content:
                                delta["content"] = chunk.delta_content
                            if chunk.delta_reasoning:
                                delta["reasoning_content"] = chunk.delta_reasoning
                            payload = {
                                "id": chunk.id,
                                "object": "chat.completion.chunk",
                                "model": cfg.model_name,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": delta,
                                        "finish_reason": chunk.finish_reason,
                                    }
                                ],
                            }
                            if chunk.prompt_tokens is not None:
                                payload["usage"] = {
                                    "prompt_tokens": chunk.prompt_tokens,
                                    "completion_tokens": chunk.completion_tokens or 0,
                                    "total_tokens": (chunk.prompt_tokens or 0)
                                    + (chunk.completion_tokens or 0),
                                }
                                payload["choices"] = []
                            yield f"data: {json.dumps(payload)}\n\n".encode()
                        yield b"data: [DONE]\n\n"

                return StreamingResponse(oai_stream(), media_type="text/event-stream")
            async with svc._lock:
                result = await provider.complete(req)
            return {
                "id": result.id,
                "object": "chat.completion",
                "model": cfg.model_name,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": result.content,
                            "reasoning_content": result.reasoning or None,
                        },
                        "finish_reason": result.finish_reason,
                    }
                ],
                "usage": {
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "total_tokens": result.prompt_tokens + result.completion_tokens,
                },
            }

        async def persisted() -> AsyncIterator[bytes]:
            async for event in svc.chat(
                message=str(user_text),
                conversation_id=body.conversation_id,
                stream=True,
                system=system if isinstance(system, str) else None,
                temperature=body.temperature,
                top_p=body.top_p,
                top_k=body.top_k,
                max_tokens=body.max_tokens,
                enable_thinking=body.enable_thinking,
                owner_id=_owner(request),
            ):
                if event["event"] == "delta":
                    delta = {"role": "assistant"}
                    if "content" in event["data"]:
                        delta["content"] = event["data"]["content"]
                    if "reasoning" in event["data"]:
                        delta["reasoning_content"] = event["data"]["reasoning"]
                    payload = {
                        "id": "chatcmpl-local",
                        "object": "chat.completion.chunk",
                        "model": cfg.model_name,
                        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(payload)}\n\n".encode()
                elif event["event"] == "done":
                    payload = {
                        "id": "chatcmpl-local",
                        "object": "chat.completion.chunk",
                        "model": cfg.model_name,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {},
                                "finish_reason": event["data"]["finish_reason"],
                            }
                        ],
                        "usage": event["data"]["usage"],
                    }
                    yield f"data: {json.dumps(payload)}\n\n".encode()
            yield b"data: [DONE]\n\n"

        if body.stream:
            return StreamingResponse(persisted(), media_type="text/event-stream")

        meta = None
        done = None
        err = None
        async for event in svc.chat(
            message=str(user_text),
            conversation_id=body.conversation_id,
            stream=False,
            system=system if isinstance(system, str) else None,
            temperature=body.temperature,
            top_p=body.top_p,
            top_k=body.top_k,
            max_tokens=body.max_tokens,
            enable_thinking=body.enable_thinking,
            owner_id=_owner(request),
        ):
            if event["event"] == "meta":
                meta = event["data"]
            elif event["event"] == "done":
                done = event["data"]
            elif event["event"] == "error":
                err = event
        if err:
            return JSONResponse(err["data"], status_code=err.get("status") or 502)
        return {
            "id": (done or {}).get("message", {}).get("id"),
            "object": "chat.completion",
            "model": cfg.model_name,
            "conversation_id": (meta or {}).get("conversation_id"),
            "choices": [
                {
                    "index": 0,
                    "message": (done or {}).get("message"),
                    "finish_reason": (done or {}).get("finish_reason"),
                }
            ],
            "usage": (done or {}).get("usage"),
        }

    return app


app = create_app()
