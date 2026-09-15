from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import sqlite3
import subprocess
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.auth import AuthRateMiddleware
from app.config import Settings, settings as default_settings
from app.db import init_db
from app.errors import error_body, install_error_handlers
from app.security import (
    SESSION_COOKIE,
    allowed_origins,
    apply_private_cache_headers,
    configured_mode,
    cookie_name,
    cookie_should_be_secure,
)
from app.providers.mlx import MlxProvider
from app.services import accounts
from app.services.chat import ChatService
from app.services.chat_lifecycle import parked_http_body
from app.services.media import MediaService
from app.services.memory import MemoryService
from app.services.heartbeat import iterate_with_heartbeats
from app.services.sampling import resolve_sampling
from app.services.stream_protocol import StreamLedger
from app.services.models import ModelManager
from app.services.tokens import TokenEstimator

logger = logging.getLogger(__name__)


class ChatBody(BaseModel):
    message: str = ""
    conversation_id: str | None = None
    regenerate: bool = False
    continue_generation: bool = False
    profile: str | None = None
    system: str | None = None
    stream: bool = True
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    presence_penalty: float | None = None
    presence_context_size: int | None = None
    frequency_penalty: float | None = None
    frequency_context_size: int | None = None
    repetition_penalty: float | None = None
    repetition_context_size: int | None = None
    max_tokens: int | None = None
    enable_thinking: bool | None = None
    reasoning_effort: str | None = None
    thinking_continuation: bool | None = None


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
    remember_me: bool = False


class MemoryPatchBody(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    key: str | None = None
    importance: float | None = Field(default=None, ge=0, le=1)


class RegisterBody(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class ModelDownloadBody(BaseModel):
    repo_id: str = Field(min_length=3, max_length=200)
    revision: str | None = Field(default=None, max_length=120)
    activate: bool = False

    @field_validator("repo_id")
    @classmethod
    def validate_repo_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*", value):
            raise ValueError("repo_id must be an owner/name Hugging Face repository")
        return value


class GenerateBody(BaseModel):
    kind: str = Field(pattern="^(image|video)$")
    prompt: str = Field(min_length=1, max_length=4000)
    backend: str | None = None
    width: int | None = Field(default=None, ge=256, le=2048)
    height: int | None = Field(default=None, ge=256, le=2048)
    steps: int | None = Field(default=None, ge=1, le=80)
    seed: int | None = Field(default=None, ge=0)
    frames: int | None = Field(default=None, ge=17, le=33)
    fps: int | None = Field(default=None, ge=8, le=30)
    preset: str | None = None
    output_resolution: str | None = None
    prompt_mode: str | None = Field(default="enhanced", pattern="^(raw|enhanced|translate_enhance)$")


class OpenAIChatBody(BaseModel):
    model: str | None = None
    messages: list[dict[str, Any]]
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    presence_penalty: float | None = None
    presence_context_size: int | None = None
    frequency_penalty: float | None = None
    frequency_context_size: int | None = None
    repetition_penalty: float | None = None
    repetition_context_size: int | None = None
    max_tokens: int | None = None
    stream: bool = False
    stream_options: dict[str, Any] | None = None
    conversation_id: str | None = None
    store: bool = False
    enable_thinking: bool | None = None
    profile: str | None = None
    tools: list[dict[str, Any]] | None = None


def _sse(event: str, data: Any) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    if event == "data":
        return f"data: {payload}\n\n".encode("utf-8")
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def create_app(settings: Settings | None = None, chat: ChatService | None = None, media: MediaService | None = None) -> FastAPI:
    cfg = settings or default_settings
    cfg.validate_private_startup()

    def _owner(request: Request) -> str | None:
        return getattr(request.state, "user_id", None)

    def _is_owner_role(request: Request) -> bool:
        user = getattr(request.state, "user", None)
        if user is None:
            return configured_mode(cfg) == "local"
        return getattr(user, "role", "user") == "owner"

    def _require_owner_role(request: Request):
        if _is_owner_role(request):
            return None
        return error_body("admin required", "authentication_error", "admin_required", status=403)

    def _cookie_token(request: Request) -> str:
        return (
            request.cookies.get(cookie_name(secure=True))
            or request.cookies.get(cookie_name(secure=False))
            or request.cookies.get(SESSION_COOKIE)
            or ""
        )

    def _session_cookie(
        resp: JSONResponse,
        token: str,
        *,
        request: Request,
        remember: bool,
    ) -> JSONResponse:
        secure = cookie_should_be_secure(request, cfg)
        name = cookie_name(secure=secure)
        kwargs: dict[str, Any] = {
            "httponly": True,
            "samesite": "strict",
            "secure": secure,
            "path": "/",
        }
        if remember:
            kwargs["max_age"] = max(1, cfg.session_remember_days) * 24 * 3600
        resp.set_cookie(name, token, **kwargs)
        apply_private_cache_headers(resp)
        return resp

    def _clear_session_cookie(resp: JSONResponse, request: Request) -> JSONResponse:
        secure = cookie_should_be_secure(request, cfg)
        for name in {cookie_name(secure=True), cookie_name(secure=False), SESSION_COOKIE}:
            resp.delete_cookie(
                name,
                path="/",
                secure=secure if name.startswith("__Host-") else (name == cookie_name(secure=True) or secure),
                httponly=True,
                samesite="strict",
            )
        apply_private_cache_headers(resp)
        return resp

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(cfg.sqlite_path)
        ModelManager.restore_active_selection(cfg)
        if cfg.bootstrap_username and cfg.bootstrap_password:
            try:
                accounts.ensure_bootstrap(cfg.bootstrap_username, cfg.bootstrap_password)
            except ValueError:
                pass
        if chat is None:
            provider = MlxProvider(cfg)
            tokenizer = TokenEstimator(cfg.model_path, trust_remote_code=cfg.trust_remote_code)
            app.state.provider = provider
            app.state.chat = ChatService(cfg, provider, tokenizer, MemoryService())
        else:
            app.state.chat = chat
            app.state.provider = getattr(chat, "provider", None)
        app.state.models = ModelManager(
            cfg,
            on_activated=lambda: setattr(
                app.state.chat,
                "tokenizer",
                TokenEstimator(cfg.model_path, trust_remote_code=cfg.trust_remote_code),
            ),
        )
        media_svc = media or MediaService(cfg)
        media_svc.recover_stale()
        app.state.media = media_svc
        app.state.chat_lifecycle = media_svc.lifecycle
        app.state.settings = cfg
        try:
            if media is None and chat is None and cfg.pause_chat_for_video:
                from app.services.media_runtime import _health_ok, restore_mlx

                if _health_ok(cfg.mlx_health_url()):
                    media_svc.lifecycle.state = "running"
                else:
                    await asyncio.to_thread(restore_mlx, cfg)
                    media_svc.lifecycle.state = "running"
        except Exception:
            from app.services.media_runtime import _health_ok as _ok

            media_svc.lifecycle.state = (
                "running" if _ok(cfg.mlx_health_url()) else "recovery_failed"
            )
        try:
            yield
        finally:
            provider = getattr(app.state, "provider", None)
            if provider is not None and hasattr(provider, "aclose"):
                await provider.aclose()

    private = configured_mode(cfg) == "private"
    gated = private or bool(cfg.bootstrap_username or cfg.bootstrap_password)
    docs = None if gated else "/docs"
    app = FastAPI(
        title="Kiln",
        version="0.6.5",
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
        settings=cfg,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(allowed_origins(cfg)),
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
        hide_internal = configured_mode(cfg) == "private"
        base = "" if hide_internal else cfg.mlx_base_url
        media_svc: MediaService | None = getattr(request.app.state, "media", None)
        chat_life = media_svc.lifecycle.snapshot() if media_svc is not None else None
        chat = getattr(request.app.state, "chat", None)
        inference = chat.inference_status() if chat is not None else {"ready": reachable}
        status = "ok" if reachable and inference.get("ready", True) else "degraded"
        return {
            "status": status,
            "provider": {
                "name": getattr(provider, "name", "mlx"),
                "reachable": reachable,
                "base_url": base,
                "http_alive": reachable,
            },
            "inference": {
                "ready": bool(inference.get("ready")),
                "consecutive_timeouts": inference.get("consecutive_timeouts", 0),
                "last_error": inference.get("last_error"),
            },
            "chat": chat_life,
            "model": cfg.model_name,
            "context_window": cfg.context_window,
            "practical_prompt_budget": cfg.practical_prompt_budget,
            "default_max_tokens": cfg.default_max_tokens,
            "max_tokens_cap": cfg.max_tokens_cap,
            "enable_thinking": cfg.enable_thinking,
            "default_profile": cfg.default_profile,
        }

    @app.get("/auth/status")
    async def auth_status(request: Request):
        n = accounts.user_count()
        private = configured_mode(cfg) == "private"
        required = private
        user = getattr(request.state, "user", None)
        ready = (not private) or n > 0
        signup = bool(cfg.auth_signup) and not private
        if not private and n == 0:
            signup = True
        return {
            "required": required,
            "ok": (not required) or user is not None,
            "setup": False if private else n == 0,
            "signup": signup,
            "username": user.username if user else None,
            "role": getattr(user, "role", None) if user else None,
            "ready": ready,
            "exposure": "private" if private else "local",
        }

    @app.post("/auth/register")
    async def auth_register(body: RegisterBody, request: Request):
        n = accounts.user_count()
        if configured_mode(cfg) == "private" and n == 0:
            return error_body(
                "owner account is not ready",
                "authentication_error",
                "not_ready",
                status=503,
            )
        if n > 0 and not cfg.auth_signup:
            return error_body(
                "signup disabled",
                "authentication_error",
                "signup_disabled",
                status=403,
            )
        if configured_mode(cfg) == "private" and not cfg.auth_signup:
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
        token = accounts.create_session(
            user.id,
            remember=False,
            idle_minutes=cfg.session_idle_minutes,
            absolute_hours=cfg.session_absolute_hours,
            remember_days=cfg.session_remember_days,
        )
        resp = JSONResponse(
            {"ok": True, "required": True, "username": user.username, "setup": False, "role": user.role}
        )
        return _session_cookie(resp, token, request=request, remember=False)

    @app.post("/auth/login")
    async def auth_login(body: LoginBody, request: Request):
        if accounts.user_count() == 0:
            if configured_mode(cfg) == "private":
                return error_body(
                    "owner account is not ready",
                    "authentication_error",
                    "not_ready",
                    status=503,
                )
            return error_body(
                "invalid username or password",
                "authentication_error",
                "auth_failed",
                status=401,
            )
        user = accounts.authenticate(body.username, body.password)
        if user is None:
            return error_body(
                "invalid username or password",
                "authentication_error",
                "auth_failed",
                status=401,
            )
        token = accounts.create_session(
            user.id,
            remember=bool(body.remember_me),
            idle_minutes=cfg.session_idle_minutes,
            absolute_hours=cfg.session_absolute_hours,
            remember_days=cfg.session_remember_days,
        )
        resp = JSONResponse(
            {"ok": True, "required": True, "username": user.username, "role": user.role}
        )
        return _session_cookie(resp, token, request=request, remember=bool(body.remember_me))

    @app.post("/auth/logout")
    async def auth_logout(request: Request):
        accounts.revoke_session(_cookie_token(request))
        resp = JSONResponse({"ok": True})
        return _clear_session_cookie(resp, request)

    @app.post("/auth/lock")
    async def auth_lock(request: Request):
        accounts.revoke_session(_cookie_token(request))
        resp = JSONResponse({"ok": True, "locked": True})
        return _clear_session_cookie(resp, request)

    @app.get("/auth/sessions")
    async def auth_sessions(request: Request):
        user = getattr(request.state, "user", None)
        if user is None:
            return error_body(
                "authentication required",
                "authentication_error",
                "auth_required",
                status=401,
            )
        return {"object": "list", "data": accounts.list_sessions(user.id, _cookie_token(request))}

    @app.delete("/auth/sessions/{session_id}")
    async def auth_revoke_session(session_id: str, request: Request):
        user = getattr(request.state, "user", None)
        if user is None:
            return error_body(
                "authentication required",
                "authentication_error",
                "auth_required",
                status=401,
            )
        ok = accounts.revoke_session_id(user.id, session_id, _cookie_token(request))
        if not ok:
            return error_body("session not found", "not_found_error", "session_not_found", status=404)
        return {"ok": True}

    @app.post("/auth/logout-all")
    async def auth_logout_all(request: Request):
        user = getattr(request.state, "user", None)
        if user is None:
            return error_body(
                "authentication required",
                "authentication_error",
                "auth_required",
                status=401,
            )
        accounts.revoke_all_sessions(user.id)
        resp = JSONResponse({"ok": True})
        return _clear_session_cookie(resp, request)

    @app.post("/auth/logout-others")
    async def auth_logout_others(request: Request):
        user = getattr(request.state, "user", None)
        if user is None:
            return error_body(
                "authentication required",
                "authentication_error",
                "auth_required",
                status=401,
            )
        n = accounts.revoke_other_sessions(user.id, _cookie_token(request))
        return {"ok": True, "revoked": n}

    @app.get("/context")
    async def global_context(request: Request):
        return request.app.state.chat.global_context()

    @app.get("/models/local")
    async def list_local_models(request: Request):
        denied = _require_owner_role(request)
        if denied is not None and configured_mode(cfg) == "private":
            return denied
        return request.app.state.models.list_local()

    @app.get("/models/catalog")
    async def search_model_catalog(
        request: Request,
        q: str = Query("", max_length=120),
        limit: int = Query(24, ge=1, le=48),
        mlx_only: bool = Query(False),
    ):
        denied = _require_owner_role(request)
        if denied is not None:
            return denied
        try:
            return await asyncio.to_thread(
                request.app.state.models.search_catalog, q.strip(), limit, mlx_only
            )
        except Exception:  # The Hub error can contain request details; keep them server-side.
            return error_body(
                "Hugging Face catalog is temporarily unavailable",
                "api_error",
                "model_catalog_unavailable",
                status=503,
            )

    @app.post("/models/download", status_code=202)
    async def download_model(body: ModelDownloadBody, request: Request):
        denied = _require_owner_role(request)
        if denied is not None:
            return denied
        try:
            queued = request.app.state.models.queue_download(
                body.repo_id, body.revision, body.activate
            )
            return await queued if inspect.isawaitable(queued) else queued
        except ValueError as exc:
            return error_body(str(exc), "invalid_request_error", "model_not_mlx", status=400)
        except RuntimeError as exc:
            return error_body(str(exc), "api_error", "model_download_unavailable", status=409)
        except Exception:  # Hub/network errors may include transport details.
            return error_body(
                "Hugging Face is temporarily unavailable",
                "api_error",
                "model_download_unavailable",
                status=503,
            )

    @app.get("/models/download")
    async def list_model_downloads(request: Request):
        denied = _require_owner_role(request)
        if denied is not None:
            return denied
        return request.app.state.models.list_jobs()

    @app.post("/models/{model_id}/activate", status_code=202)
    async def activate_model(model_id: str, request: Request):
        denied = _require_owner_role(request)
        if denied is not None:
            return denied
        try:
            result = await asyncio.to_thread(request.app.state.models.activate, model_id)
        except ValueError as exc:
            return error_body("model is not installed", "not_found_error", "model_not_found", status=404)
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            logger.exception("Model activation failed")
            return error_body(
                "Model activation failed. Check server logs.",
                "api_error",
                "model_switch_failed",
                status=409,
            )
        return result

    @app.get("/memory")
    async def list_memories(
        request: Request,
        q: str = Query(""),
        limit: int = Query(20, ge=1, le=100),
    ):
        recs = request.app.state.chat.memory.search(
            q, limit=limit, owner_id=_owner(request)
        )
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
                user_id=_owner(request),
            )
        )
        return {"id": rec.id, "content": rec.content}

    @app.get("/memory/{memory_id}")
    async def get_memory(memory_id: str, request: Request):
        rec = request.app.state.chat.memory.get(memory_id, _owner(request))
        if rec is None:
            return error_body("memory not found", "not_found_error", "memory_not_found", status=404)
        return {
            "id": rec.id,
            "type": rec.memory_type,
            "key": rec.key,
            "content": rec.content,
            "importance": rec.importance,
        }

    @app.patch("/memory/{memory_id}")
    async def patch_memory(memory_id: str, body: MemoryPatchBody, request: Request):
        fields: dict[str, object] = {}
        if body.content is not None:
            fields["content"] = body.content
        if body.key is not None:
            fields["key"] = body.key
        if body.importance is not None:
            fields["importance"] = body.importance
        rec = request.app.state.chat.memory.update(memory_id, _owner(request), **fields)
        if rec is None:
            return error_body("memory not found", "not_found_error", "memory_not_found", status=404)
        return {"id": rec.id, "content": rec.content}

    @app.delete("/memory/{memory_id}")
    async def delete_memory(memory_id: str, request: Request):
        ok = request.app.state.chat.memory.delete(memory_id, _owner(request))
        if not ok:
            return error_body("memory not found", "not_found_error", "memory_not_found", status=404)
        return {"ok": True}

    def _chat_parked_response(request: Request):
        life = getattr(request.app.state, "chat_lifecycle", None)
        if life is not None and life.is_unavailable():
            return JSONResponse(parked_http_body(), status_code=503)
        return None

    @app.post("/chat")
    async def chat_endpoint(body: ChatBody, request: Request):
        parked = _chat_parked_response(request)
        if parked is not None:
            return parked
        svc: ChatService = request.app.state.chat

        def _chat_kwargs(**extra: Any) -> dict[str, Any]:
            return {
                "message": body.message,
                "conversation_id": body.conversation_id,
                "regenerate": body.regenerate,
                "continue_generation": body.continue_generation,
                "profile": body.profile,
                "system": body.system,
                "temperature": body.temperature,
                "top_p": body.top_p,
                "top_k": body.top_k,
                "min_p": body.min_p,
                "presence_penalty": body.presence_penalty,
                "presence_context_size": body.presence_context_size,
                "frequency_penalty": body.frequency_penalty,
                "frequency_context_size": body.frequency_context_size,
                "repetition_penalty": body.repetition_penalty,
                "repetition_context_size": body.repetition_context_size,
                "max_tokens": body.max_tokens,
                "enable_thinking": body.enable_thinking,
                "reasoning_effort": body.reasoning_effort,
                "thinking_continuation": body.thinking_continuation,
                "owner_id": _owner(request),
                **extra,
            }

        async def event_stream() -> AsyncIterator[bytes]:
            agen = svc.chat(**_chat_kwargs(stream=True))
            stream = iterate_with_heartbeats(agen, cfg.heartbeat_s)
            try:
                async for event in stream:
                    if await request.is_disconnected():
                        await stream.aclose()
                        return
                    yield _sse(event["event"], event["data"])
                yield b"data: [DONE]\n\n"
            except (asyncio.CancelledError, GeneratorExit):
                await stream.aclose()
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
        async for event in svc.chat(**_chat_kwargs(stream=False)):
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

    @app.delete("/conversation/{conversation_id}/message/{message_id}")
    async def delete_message(conversation_id: str, message_id: str, request: Request):
        ok = request.app.state.chat.delete_message(
            conversation_id, message_id, owner_id=_owner(request)
        )
        if not ok:
            return error_body(
                "message not found",
                "not_found_error",
                "message_not_found",
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

    @app.get("/generate/backends")
    async def generate_backends(request: Request):
        media: MediaService = request.app.state.media
        return media.backends()

    @app.post("/generate/compile")
    async def compile_generate_prompt(body: GenerateBody, request: Request):
        from app.services.prompt_compiler import compile_visual_prompt

        mode = body.prompt_mode or "enhanced"
        try:
            got = await asyncio.to_thread(
                compile_visual_prompt, body.prompt, body.kind, mode
            )
        except ValueError as exc:
            return error_body(str(exc), "invalid_request_error", "invalid_body", status=400)
        except RuntimeError as exc:
            return error_body(str(exc), "dependency_error", "compiler_unavailable", status=503)
        return {
            "kind": got.kind,
            "prompt_mode": got.mode,
            "original_prompt": got.original,
            "effective_prompt": got.effective,
            "violations": got.violations,
            "compiler_model": got.compiler_model,
        }

    @app.get("/generate")
    async def list_generate_jobs(request: Request, limit: int = Query(20, ge=1, le=50)):
        media: MediaService = request.app.state.media
        return {"object": "list", "data": media.list_jobs(_owner(request), limit=limit)}

    @app.post("/generate")
    async def create_generate_job(body: GenerateBody, request: Request):
        media: MediaService = request.app.state.media
        params = {k: v for k, v in {
            "width": body.width, "height": body.height, "steps": body.steps, "seed": body.seed,
            "frames": body.frames, "fps": body.fps, "preset": body.preset,
            "output_resolution": body.output_resolution,
            "prompt_mode": body.prompt_mode or "enhanced",
        }.items() if v is not None}
        try:
            job = media.enqueue(kind=body.kind, prompt=body.prompt, backend=body.backend, params=params, owner_id=_owner(request))
        except ValueError as exc:
            return error_body(str(exc), "invalid_request_error", "invalid_body", status=400)
        asyncio.create_task(media.pump())
        return job

    @app.get("/generate/{job_id}")
    async def get_generate_job(job_id: str, request: Request):
        media: MediaService = request.app.state.media
        job = media.get(job_id, _owner(request))
        if job is None:
            return error_body("job not found", "not_found_error", "job_not_found", status=404)
        return job

    @app.post("/generate/{job_id}/cancel")
    async def cancel_generate_job(job_id: str, request: Request):
        media: MediaService = request.app.state.media
        job = media.cancel(job_id, _owner(request))
        if job is None:
            return error_body("job not found", "not_found_error", "job_not_found", status=404)
        asyncio.create_task(media.pump())
        return job

    @app.get("/generate/{job_id}/file")
    async def get_generate_file(job_id: str, request: Request):
        media: MediaService = request.app.state.media
        path = media.output_path(job_id, _owner(request))
        if path is None:
            return error_body("file not found", "not_found_error", "file_not_found", status=404)
        media_type = "video/mp4" if path.suffix.lower() == ".mp4" else "image/png"
        return FileResponse(path, media_type=media_type, filename=path.name)

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
        parked = _chat_parked_response(request)
        if parked is not None:
            return parked
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
            thinking = cfg.enable_thinking if body.enable_thinking is None else body.enable_thinking
            sampled = resolve_sampling(
                enable_thinking=thinking,
                temperature=body.temperature,
                top_p=body.top_p,
                top_k=body.top_k,
                min_p=body.min_p,
                presence_penalty=body.presence_penalty,
                presence_context_size=body.presence_context_size,
                frequency_penalty=body.frequency_penalty,
                frequency_context_size=body.frequency_context_size,
                repetition_penalty=body.repetition_penalty,
                repetition_context_size=body.repetition_context_size,
            )
            req = ChatRequest(
                messages=mapped,
                temperature=sampled["temperature"],
                top_p=sampled["top_p"],
                top_k=sampled["top_k"],
                min_p=sampled["min_p"],
                presence_penalty=sampled["presence_penalty"],
                presence_context_size=sampled["presence_context_size"],
                frequency_penalty=sampled["frequency_penalty"],
                frequency_context_size=sampled["frequency_context_size"],
                repetition_penalty=sampled["repetition_penalty"],
                repetition_context_size=sampled["repetition_context_size"],
                max_tokens=max_out,
                enable_thinking=thinking,
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
                    ledger = StreamLedger()
                    last_id = "chatcmpl-local"
                    async with svc._lock:
                        async for chunk in provider.stream(req):
                            last_id = chunk.id or last_id
                            if chunk.wire_done:
                                ledger.observe_done_wire()
                                continue
                            if chunk.malformed:
                                ledger.malformed_frames += 1
                                continue
                            if chunk.http_eof:
                                ledger.http_eof = True
                                continue
                            if chunk.finish_reason:
                                ledger.observe_finish(chunk.finish_reason)
                            if not (
                                chunk.delta_content
                                or chunk.delta_reasoning
                                or chunk.prompt_tokens is not None
                            ):
                                continue
                            payload: dict[str, Any] = {
                                "id": last_id,
                                "object": "chat.completion.chunk",
                                "model": cfg.model_name,
                            }
                            if chunk.prompt_tokens is not None and not (
                                chunk.delta_content or chunk.delta_reasoning
                            ):
                                payload["choices"] = []
                                payload["usage"] = {
                                    "prompt_tokens": chunk.prompt_tokens,
                                    "completion_tokens": chunk.completion_tokens or 0,
                                    "total_tokens": (chunk.prompt_tokens or 0)
                                    + (chunk.completion_tokens or 0),
                                }
                            else:
                                delta: dict[str, Any] = {"role": "assistant"}
                                if chunk.delta_content:
                                    delta["content"] = chunk.delta_content
                                if chunk.delta_reasoning:
                                    delta["reasoning_content"] = chunk.delta_reasoning
                                payload["choices"] = [
                                    {
                                        "index": 0,
                                        "delta": delta,
                                        "finish_reason": None,
                                    }
                                ]
                            yield f"data: {json.dumps(payload)}\n\n".encode()
                    finish = ledger.stored_finish_reason(ledger.classify())
                    yield f"data: {json.dumps({'id': last_id, 'object': 'chat.completion.chunk', 'model': cfg.model_name, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]})}\n\n".encode()
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
                profile=body.profile,
                system=system if isinstance(system, str) else None,
                temperature=body.temperature,
                top_p=body.top_p,
                top_k=body.top_k,
                min_p=body.min_p,
                presence_penalty=body.presence_penalty,
                presence_context_size=body.presence_context_size,
                frequency_penalty=body.frequency_penalty,
                frequency_context_size=body.frequency_context_size,
                repetition_penalty=body.repetition_penalty,
                repetition_context_size=body.repetition_context_size,
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
                elif event["event"] == "error":
                    err = event["data"].get("error") or {}
                    payload = {
                        "id": "chatcmpl-local",
                        "object": "chat.completion.chunk",
                        "model": cfg.model_name,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {},
                                "finish_reason": err.get("code") or "generation_error",
                            }
                        ],
                        "error": err,
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
            profile=body.profile,
            system=system if isinstance(system, str) else None,
            temperature=body.temperature,
            top_p=body.top_p,
            top_k=body.top_k,
            min_p=body.min_p,
            presence_penalty=body.presence_penalty,
            presence_context_size=body.presence_context_size,
            frequency_penalty=body.frequency_penalty,
            frequency_context_size=body.frequency_context_size,
            repetition_penalty=body.repetition_penalty,
            repetition_context_size=body.repetition_context_size,
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


def __getattr__(name: str):
    if name == "app":
        return create_app()
    raise AttributeError(name)
