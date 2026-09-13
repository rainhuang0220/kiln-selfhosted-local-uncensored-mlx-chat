from __future__ import annotations

import time
from ipaddress import ip_address
from collections import defaultdict, deque
from typing import Deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import settings as default_settings
from app.errors import error_body
from app.security import (
    apply_private_cache_headers,
    auth_required,
    cookie_name,
    csrf_protected,
    exposure_for,
    origin_allowed,
)
from app.services.accounts import resolve_api_token, resolve_session, user_count

PUBLIC_EXACT = {
    "/auth/login",
    "/auth/status",
    "/auth/logout",
    "/auth/register",
}
PUBLIC_PREFIX = ("/docs", "/redoc", "/openapi.json")


class AuthRateMiddleware(BaseHTTPMiddleware):
    """Opaque session cookie; login rate limit; body size cap; CSRF origin."""

    def __init__(
        self,
        app,
        chat_per_minute: int = 20,
        login_per_minute: int = 5,
        max_request_bytes: int = 1_048_576,
        trust_proxy_headers: bool = False,
        settings=None,
    ):
        super().__init__(app)
        self.chat_per_minute = chat_per_minute
        self.login_per_minute = login_per_minute
        self.max_request_bytes = max_request_bytes
        self.trust_proxy_headers = trust_proxy_headers
        self.settings = settings or default_settings
        self._hits: dict[str, Deque[float]] = defaultdict(deque)
        self._logins: dict[str, Deque[float]] = defaultdict(deque)

    def _cookie_token(self, request: Request) -> str:
        secure_name = cookie_name(secure=True)
        insecure_name = cookie_name(secure=False)
        return request.cookies.get(secure_name) or request.cookies.get(insecure_name) or ""

    def _authed_user(self, request: Request):
        bearer = request.headers.get("authorization") or ""
        if bearer.lower().startswith("bearer "):
            api_user = resolve_api_token(bearer[7:].strip())
            if api_user is not None:
                request.state.auth_via = "api_token"
                return api_user
            request.state.auth_via = "none"
            return None
        token = self._cookie_token(request)
        request.state.session_token = token
        user = resolve_session(token)
        request.state.auth_via = "cookie" if user else "none"
        return user

    def _window_ok(self, bucket: dict[str, Deque[float]], ip: str, limit: int) -> bool:
        now = time.monotonic()
        q = bucket[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    def _rate_ok(self, ip: str, path: str) -> bool:
        if path in {"/auth/login", "/auth/register"}:
            return self._window_ok(self._logins, ip, self.login_per_minute)
        if path not in {"/chat", "/v1/chat/completions", "/generate"}:
            return True
        return self._window_ok(self._hits, ip, self.chat_per_minute)

    def _client_ip(self, request: Request) -> str:
        direct = request.client.host if request.client else "unknown"
        if not self.trust_proxy_headers:
            return direct
        forwarded = request.headers.get("x-real-ip", "").strip()
        try:
            return str(ip_address(forwarded))
        except ValueError:
            return direct

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        request.state.user = None
        request.state.user_id = None
        request.state.session_token = ""
        request.state.auth_via = "none"
        request.state.settings = self.settings
        if request.method == "OPTIONS":
            return await call_next(request)
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > self.max_request_bytes:
            return error_body(
                "request too large",
                "invalid_request_error",
                "request_too_large",
                status=413,
            )
        n = user_count()
        needed = auth_required(request, self.settings, n)
        private = exposure_for(request, self.settings) == "private"
        request.state.exposure = "private" if private else "local"
        request.state.auth_needed = needed
        public = path in PUBLIC_EXACT or path == "/health"
        if needed and path.startswith(PUBLIC_PREFIX):
            public = False
        if private and n == 0:
            if path not in {"/auth/status"}:
                if path in {"/auth/login", "/auth/register"}:
                    return error_body(
                        "owner account is not ready",
                        "authentication_error",
                        "not_ready",
                        status=503,
                    )
                if path == "/health":
                    public = True
                elif not public:
                    return error_body(
                        "authentication required",
                        "authentication_error",
                        "auth_required",
                        status=401,
                    )
        user = self._authed_user(request)
        request.state.user = user
        request.state.user_id = user.id if user else None
        if needed and not public and user is None:
            return error_body(
                "authentication required",
                "authentication_error",
                "auth_required",
                status=401,
            )
        if csrf_protected(request) and request.state.auth_via != "api_token":
            if private or (needed and user is not None) or path.startswith("/auth/"):
                if not origin_allowed(request, self.settings):
                    return error_body(
                        "origin not allowed",
                        "authentication_error",
                        "csrf_rejected",
                        status=403,
                    )
        client = self._client_ip(request)
        if needed and not self._rate_ok(client, path):
            return error_body(
                "rate limit exceeded",
                "rate_limit_error",
                "too_many_requests",
                status=429,
            )
        response = await call_next(request)
        if isinstance(response, Response):
            apply_private_cache_headers(response)
        return response
