"""Separate transport, model HTTP, inference, and deliberate suspension.

GET /health must stay a read of these signals. It does not generate.
"""

from __future__ import annotations

from typing import Any


def describe_gateway(
    *,
    http_alive: bool,
    chat_state: str | None,
    inference_capability: str,
    busy: bool,
    last_verified_at: int | None,
    verification_method: str | None = None,
    evidence_expires_at: int | None = None,
) -> dict[str, Any]:
    suspension: str | None = None
    capability = "BUSY" if busy else inference_capability
    if chat_state in {"parking", "parked"}:
        state = "VIDEO_SUSPENDED"
        suspension = "video"
    elif chat_state == "restoring":
        state = "STARTING"
        suspension = "video_restore"
    elif chat_state == "recovery_failed":
        state = "DEGRADED"
        suspension = "video_restore_failed"
    elif capability == "BUSY":
        state = "BUSY"
    elif not http_alive:
        state = "OFFLINE"
    elif capability in {"DEGRADED", "FAILED"}:
        state = "DEGRADED"
    else:
        state = "AVAILABLE"
    return {
        "state": state,
        "transport_status": "ok" if http_alive else "unreachable",
        "model_status": "http_ok" if http_alive else "http_down",
        "inference_status": capability.lower(),
        "inference_capability": capability,
        "suspension_reason": suspension,
        "last_verified_at": last_verified_at,
        "verification_method": verification_method,
        "evidence_expires_at": evidence_expires_at,
    }
