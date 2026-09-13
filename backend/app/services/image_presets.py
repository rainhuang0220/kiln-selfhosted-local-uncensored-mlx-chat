"""Product image presets. Fast is Z-Image Turbo; Quality is FLUX.1-dev."""
from __future__ import annotations

from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        "id": "fast",
        "label": "Fast",
        "backend": "z-image-turbo",
        "width": 1024,
        "height": 1024,
        "steps": 9,
        "guidance": None,
        "typical_wall_s": 240,
        "typical_note": "Typically about 3–6 minutes on M4 24GB. Chat stays up.",
        "hint": "Z-Image Turbo Q4. Fast distill; weaker exact count and action landing.",
        "recommended": True,
    },
    "quality": {
        "id": "quality",
        "label": "Quality",
        "backend": "flux1-dev",
        "width": 1024,
        "height": 1024,
        "steps": 20,
        "guidance": 3.5,
        "typical_wall_s": 660,
        "typical_note": "Measured ~10–12 minutes per 1024² / 20-step image on M4 24GB. Chat parks for the job.",
        "hint": "FLUX.1 [dev] Q4. Better exact count and fewer invented extras than Z-Image; still misses jump-onto-table.",
        "recommended": False,
    },
}


def public_presets() -> list[dict[str, Any]]:
    keys = (
        "id",
        "label",
        "backend",
        "width",
        "height",
        "steps",
        "guidance",
        "typical_wall_s",
        "typical_note",
        "hint",
        "recommended",
    )
    return [{k: p[k] for k in keys} for p in PRESETS.values()]


def resolve(params: dict[str, Any] | None, backend: str | None) -> tuple[dict[str, Any], str | None]:
    raw = dict(params or {})
    name = str(raw.get("preset") or "")
    if name not in PRESETS:
        if backend == "flux1-dev":
            name = "quality"
        elif backend in (None, "", "z-image-turbo") and not raw.get("steps"):
            name = "fast"
        else:
            return raw, backend
    base = PRESETS[name]
    out = dict(raw)
    out["preset"] = name
    backend = str(base["backend"])
    if out.get("width") is None:
        out["width"] = base["width"]
    if out.get("height") is None:
        out["height"] = base["height"]
    if out.get("steps") is None:
        out["steps"] = base["steps"]
    if out.get("guidance") is None and base.get("guidance") is not None:
        out["guidance"] = base["guidance"]
    return out, backend
