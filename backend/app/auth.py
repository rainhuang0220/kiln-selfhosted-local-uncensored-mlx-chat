from __future__ import annotations

import time
from ipaddress import ip_address
from collections import defaultdict, deque
from typing import Deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.errors import error_body
from app.services.accounts import COOKIE, resolve_session, user_count

PUBLIC_EXACT = {
    "/health",
    "/auth/login",
    "/auth/status",
    "/auth/logout",
    "/auth/register",
}
PUBLIC_PREFIX = ("/docs", "/redoc", "/openapi.json")


class AuthRateMiddleware(BaseHTTPMiddleware):
    """Opaque session cookie; login rate limit; body size cap."""

    def __init__(
        self,
        app,
        chat_per_minute: int = 20,
        login_per_minute: int = 5,
        max_request_bytes: int = 1_048_576,
        trust_proxy_headers: bool = False,
    ):
        super().__init__(app)
        self.chat_per_minute = chat_per_minute
        self.login_per_minute = login_per_minute
        self.max_request_bytes = max_request_bytes
        self.trust_proxy_headers = trust_proxy_headers
        self._hits: dict[str, Deque[float]] = defaultdict(deque)
        self._logins: dict[str, Deque[float]] = defaultdict(deque)

    def _authed_user(self, request: Request):
        token = request.cookies.get(COOKIE) or ""
        bearer = request.headers.get("authorization") or ""
        if bearer.lower().startswith("bearer "):
            token = bearer[7:].strip() or token
        return resolve_session(token)

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
        if path not in {"/chat", "/v1/chat/completions"}:
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
        needed = user_count() > 0
        public = path in PUBLIC_EXACT or (not needed and path.startswith(PUBLIC_PREFIX))
        if needed and path.startswith(PUBLIC_PREFIX):
            public = False
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
        client = self._client_ip(request)
        if needed and not self._rate_ok(client, path):
            return error_body(
                "rate limit exceeded",
                "rate_limit_error",
                "too_many_requests",
                status=429,
            )
        return await call_next(request)
