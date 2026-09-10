"""Expand a user prompt for image/video models without changing requested facts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Literal
from urllib.request import Request, urlopen

from app.config import Settings, settings as default_settings
from app.services.constraint_verifier import structured_violations

Kind = Literal["image", "video"]
Mode = Literal["raw", "enhanced"]
CompleteFn = Callable[[str, str], str]

IMAGE_SYSTEM = """You are a prompt compiler, not a creative writer.

Preserve every explicit user constraint.
Do not remove, soften, moralize, reinterpret, or replace requested content.
Do not invent conflicting subjects/actions.
Resolve only linguistic ambiguity when necessary.
Return only a generation-ready visual prompt.

Expand the user request into a detailed still-image description.
Keep every subject, attribute, count, spatial relation, action, style, and constraint.
Chinese may be rendered as precise English while preserving those facts.
Do not add safety disclaimers or substitute a different scene.

Use this structure, then one final paragraph:
SUBJECT
ACTION
COMPOSITION
ENVIRONMENT
CAMERA
LIGHTING
STYLE
CONSTRAINTS
"""

VIDEO_SYSTEM = """You are a prompt compiler, not a creative writer.

Preserve every explicit user constraint.
Do not remove, soften, moralize, reinterpret, or replace requested content.
Do not invent conflicting subjects/actions.
Resolve only linguistic ambiguity when necessary.
Return only a generation-ready visual prompt.

Expand the user request into a short-video description.
Keep every subject, attribute, count, spatial relation, action, style, and constraint.
Emphasize: subject, appearance, initial state, action over time, camera movement,
scene movement, environment, lighting, temporal consistency.
Do not pile empty quality words such as 8K masterpiece.
Chinese may be rendered as precise English while preserving those facts.
"""

_SWAPS = (
    ("red", "blue"),
    ("blue", "red"),
    ("three", "four"),
    ("four", "three"),
    ("left", "right"),
    ("right", "left"),
    ("standing", "sitting"),
    ("sitting", "standing"),
    ("night", "daytime"),
    ("night", "day"),
)


def _word(text: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", text, flags=re.I) is not None


def preservation_violations(original: str, effective: str) -> list[str]:
    found: list[str] = []
    for keep, forbidden in _SWAPS:
        if _word(original, keep) and not _word(effective, keep):
            found.append(f"dropped:{keep}")
        if _word(original, keep) and _word(effective, forbidden) and not _word(original, forbidden):
            found.append(f"swapped:{keep}->{forbidden}")
    return list(dict.fromkeys(found))


@dataclass
class CompiledPrompt:
    original: str
    effective: str
    mode: Mode
    kind: Kind
    violations: list[str] = field(default_factory=list)
    compiler_model: str | None = None


def mlx_compiler_payload(system: str, user: str) -> dict:
    # mlx_lm.server only serves the already-loaded checkpoint as default_model.
    return {
        "model": "default_model",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "top_p": 0.8,
        "top_k": 20,
        "max_tokens": 700,
        "stream": False,
        "chat_template_kwargs": {
            "enable_thinking": False,
            "reasoning_effort": "low",
            "preserve_thinking": False,
        },
    }


def _local_complete(system: str, user: str, settings: Settings) -> str:
    body = json.dumps(mlx_compiler_payload(system, user)).encode()
    req = Request(
        settings.mlx_chat_url(),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=min(90, settings.mlx_timeout_s)) as resp:
        data = json.loads(resp.read().decode())
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    text = (message.get("content") or "").strip()
    if not text:
        raise RuntimeError("prompt compiler returned an empty completion")
    return text


def compile_visual_prompt(
    original: str,
    kind: Kind,
    mode: Mode = "enhanced",
    complete_fn: CompleteFn | None = None,
    settings: Settings | None = None,
) -> CompiledPrompt:
    text = (original or "").strip()
    if not text:
        raise ValueError("prompt is required")
    if mode not in ("raw", "enhanced"):
        raise ValueError("prompt_mode must be raw or enhanced")
    if kind not in ("image", "video"):
        raise ValueError("kind must be image or video")
    if mode == "raw":
        return CompiledPrompt(original=text, effective=text, mode=mode, kind=kind)

    cfg = settings or default_settings
    complete = complete_fn or (lambda system, user: _local_complete(system, user, cfg))
    system = IMAGE_SYSTEM if kind == "image" else VIDEO_SYSTEM
    user = f"Compile this {kind} prompt without changing any requested facts:\n\n{text}"
    try:
        drafted = complete(system, user).strip()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"prompt compiler unavailable; retry with Raw mode ({exc})") from exc
    if not drafted:
        raise RuntimeError("prompt compiler returned an empty completion")
    violations = preservation_violations(text, drafted) + structured_violations(text, drafted)
    if violations:
        return CompiledPrompt(
            original=text,
            effective=text,
            mode=mode,
            kind=kind,
            violations=violations,
            compiler_model=cfg.model_name,
        )
    return CompiledPrompt(
        original=text,
        effective=drafted,
        mode=mode,
        kind=kind,
        compiler_model=cfg.model_name,
    )
