"""Separate transport, model HTTP, inference, and deliberate suspension.

GET /health must stay a read of these signals. It does not generate.
"""

from __future__ import annotations

from typing import Any


def describe_gateway(
    *,
    http_alive: bool,
    chat_state: str | None,
    inference_ready: bool,
    busy: bool,
    last_verified_at: int | None,
) -> dict[str, Any]:
    suspension: str | None = None
    if chat_state in {"parking", "parked"}:
        state = "VIDEO_SUSPENDED"
        suspension = "video"
    elif chat_state == "restoring":
        state = "STARTING"
        suspension = "video_restore"
    elif chat_state == "recovery_failed":
        state = "DEGRADED"
        suspension = "video_restore_failed"
    elif busy:
        state = "BUSY"
    elif not http_alive:
        state = "OFFLINE"
    elif not inference_ready:
        state = "DEGRADED"
    else:
        state = "AVAILABLE"
    if state == "BUSY":
        inference_status = "busy"
    elif inference_ready:
        inference_status = "ready"
    else:
        inference_status = "degraded"
    return {
        "state": state,
        "transport_status": "ok" if http_alive else "unreachable",
        "model_status": "http_ok" if http_alive else "http_down",
        "inference_status": inference_status,
        "suspension_reason": suspension,
        "last_verified_at": last_verified_at,
    }
