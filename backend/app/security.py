"""Exposure mode, CSRF origin checks, and cookie helpers.

Private internet mode is fail-closed: authentication is required even when
the users table is empty. A public Host header cannot inherit local open mode.
"""

from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import Response

from app.config import Settings

# Names that mean loopback. "testserver"/"test" are Starlette TestClient defaults only.
LOOPBACK_NAMES = {"localhost", "::1", "testserver", "test"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SESSION_COOKIE = "kiln_session"
HOST_SESSION_COOKIE = "__Host-kiln_session"
NO_STORE = "no-store, private"


def parse_hostname(raw: str) -> str:
    host = (raw or "").strip().lower()
    if host.startswith("["):
        end = host.find("]")
        if end != -1:
            return host[1:end]
    if host.count(":") == 1:
        return host.split(":")[0]
    return host


def request_hostname(request: Request) -> str:
    return parse_hostname(request.headers.get("host") or "")


def is_loopback_host(host: str) -> bool:
    """True only for loopback. RFC1918, link-local, and empty Host are not loopback."""
    if not host:
        return False
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def is_public_hostname(host: str) -> bool:
    return not is_loopback_host(host)


def exposure_for(request: Request, settings: Settings) -> str:
    mode = (settings.kiln_exposure or "local").strip().lower()
    if mode == "private":
        return "private"
    host = request_hostname(request)
    forwarded = parse_hostname(request.headers.get("x-forwarded-host") or "")
    proto = (request.headers.get("x-forwarded-proto") or "").strip().lower()
    # HTTPS at a trusted proxy is never local-open, even if Host is spoofed to 127.0.0.1.
    if settings.trust_proxy_headers and proto == "https":
        return "private"
    if forwarded and not is_loopback_host(forwarded):
        return "private"
    if not is_loopback_host(host):
        return "private"
    return "local"


def auth_required(request: Request, settings: Settings, user_count: int) -> bool:
    if exposure_for(request, settings) == "private":
        return True
    return user_count > 0


def cookie_name(*, secure: bool) -> str:
    return HOST_SESSION_COOKIE if secure else SESSION_COOKIE


def cookie_should_be_secure(request: Request, settings: Settings) -> bool:
    if settings.cookie_secure:
        return True
    return exposure_for(request, settings) == "private"


def allowed_origins(settings: Settings) -> set[str]:
    origins = {item.rstrip("/") for item in settings.cors_origin_list()}
    origins.add("https://kiln.plainlist.space")
    origins.add("http://127.0.0.1:7777")
    origins.add("http://localhost:7777")
    origins.add("http://127.0.0.1:8787")
    origins.add("http://localhost:8787")
    return origins


def origin_allowed(request: Request, settings: Settings) -> bool:
    raw = (request.headers.get("origin") or "").strip()
    if not raw:
        referer = (request.headers.get("referer") or "").strip()
        if referer:
            parsed = urlparse(referer)
            if parsed.scheme and parsed.netloc:
                raw = f"{parsed.scheme}://{parsed.netloc}"
    if not raw:
        if exposure_for(request, settings) == "local" and is_loopback_host(request_hostname(request)):
            return True
        return False
    parsed = urlparse(raw)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return origin in allowed_origins(settings)


def csrf_protected(request: Request) -> bool:
    if request.method.upper() in SAFE_METHODS:
        return False
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return False
    return True


def apply_private_cache_headers(response: Response) -> None:
    response.headers.setdefault("Cache-Control", NO_STORE)
    response.headers.setdefault("Pragma", "no-cache")
