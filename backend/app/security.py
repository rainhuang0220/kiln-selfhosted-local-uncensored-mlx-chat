"""Explicit exposure mode. Host and user_count never select the mode."""

from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import Response

from app.config import Settings

LOOPBACK_NAMES = {"localhost", "::1"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SESSION_COOKIE = "kiln_session"
HOST_SESSION_COOKIE = "__Host-kiln_session"
NO_STORE = "no-store, private"
LOCAL_LOOPBACK_ORIGINS = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5174",
    "http://localhost:5174",
    "http://127.0.0.1:7777",
    "http://localhost:7777",
    "http://127.0.0.1:8787",
    "http://localhost:8787",
}


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
    """True only for loopback. RFC1918, link-local, test, and empty Host are not."""
    if not host:
        return False
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def configured_mode(settings: Settings) -> str:
    raw = settings.kiln_exposure
    if raw is None or str(raw).strip() == "":
        raise RuntimeError("KILN_EXPOSURE must be set to local or private")
    mode = str(raw).strip().lower()
    if mode not in {"local", "private"}:
        raise RuntimeError("KILN_EXPOSURE must be local or private")
    return mode


def validate_public_origin(raw: str) -> str:
    value = (raw or "").strip()
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise RuntimeError(
            "KILN_PUBLIC_ORIGIN must be an https origin with no path, query, or fragment"
        )
    if parsed.path == "/":
        raise RuntimeError(
            "KILN_PUBLIC_ORIGIN must be an https origin with no path, query, or fragment"
        )
    return f"https://{parsed.netloc}"


def exposure_for(_request: Request, settings: Settings) -> str:
    """Configured mode only. Request headers never select the mode."""
    return configured_mode(settings)


def auth_required(settings: Settings) -> bool:
    return configured_mode(settings) == "private"


def tenant_requires_owner(settings: Settings) -> bool:
    return configured_mode(settings) == "private"


def local_deployment_request(request: Request, settings: Settings) -> bool:
    """True when a local-mode request stays on loopback. Else tripwire."""
    del settings
    host = request_hostname(request)
    forwarded = parse_hostname(request.headers.get("x-forwarded-host") or "")
    proto = (request.headers.get("x-forwarded-proto") or "").strip().lower()
    if proto == "https":
        return False
    if forwarded and not is_loopback_host(forwarded):
        return False
    return is_loopback_host(host)


def cookie_name(*, secure: bool) -> str:
    return HOST_SESSION_COOKIE if secure else SESSION_COOKIE


def cookie_should_be_secure(_request: Request, settings: Settings) -> bool:
    if settings.cookie_secure:
        return True
    return configured_mode(settings) == "private"


def allowed_origins(settings: Settings) -> set[str]:
    if configured_mode(settings) == "private":
        return {validate_public_origin(settings.kiln_public_origin)}
    origins = set(LOCAL_LOOPBACK_ORIGINS)
    for item in settings.cors_origin_list():
        parsed = urlparse(item.rstrip("/"))
        host = parse_hostname(parsed.netloc)
        if parsed.scheme == "http" and is_loopback_host(host):
            origins.add(f"{parsed.scheme}://{parsed.netloc}")
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
