"""Product video generation presets. Fast is the old speed default; Standard is upstream-like."""
from __future__ import annotations

from typing import Any

# Training-free TeaCache threshold for Wan 1.3B (ali-vilab coefficients).
TEACACHE_THRESHOLD = 0.05
FPS = 16
WIDTH = 832
HEIGHT = 480
MAX_PRODUCT_FRAMES = 33

PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        "id": "fast",
        "label": "Fast",
        "width": WIDTH,
        "height": HEIGHT,
        "frames": 17,
        "steps": 10,
        "fps": FPS,
        "guide": 5.0,
        "shift": 5.0,
        "teacache": TEACACHE_THRESHOLD,
        "clip_s": 1.1,
        "typical_wall_s": 210,
        "typical_note": "Typically about 3–4 minutes on M4 24GB.",
        "hint": "Previous default. Guide 5, shift 5, TeaCache on. Faster; weaker adherence.",
        "recommended": False,
    },
    "standard": {
        "id": "standard",
        "label": "Quality",
        "width": WIDTH,
        "height": HEIGHT,
        "frames": 17,
        "steps": 20,
        "fps": FPS,
        "guide": 6.0,
        "shift": 8.0,
        "teacache": 0.0,
        "clip_s": 1.1,
        "typical_wall_s": 420,
        "typical_note": "Typically about 6–8 minutes on M4 24GB.",
        "hint": "Upstream-like Wan2.1 1.3B: more steps, guide 6, shift 8, TeaCache off.",
        "recommended": True,
    },
    "long": {
        "id": "long",
        "label": "Long",
        "width": WIDTH,
        "height": HEIGHT,
        "frames": 33,
        "steps": 20,
        "fps": FPS,
        "guide": 6.0,
        "shift": 8.0,
        "teacache": 0.0,
        "clip_s": 2.1,
        "typical_wall_s": 900,
        "typical_note": "Typically about 12–16 minutes on M4 24GB.",
        "hint": "About 2 seconds. Quality sampling; chat parks for the job.",
        "recommended": False,
    },
}


def public_presets() -> list[dict[str, Any]]:
    keys = (
        "id",
        "label",
        "width",
        "height",
        "frames",
        "steps",
        "fps",
        "guide",
        "shift",
        "teacache",
        "clip_s",
        "typical_wall_s",
        "typical_note",
        "hint",
        "recommended",
    )
    return [{k: p[k] for k in keys} for p in PRESETS.values()]


def resolve(params: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(params or {})
    name = str(raw.get("preset") or "standard")
    if name not in PRESETS:
        name = "standard"
    base = dict(PRESETS[name])
    frames = int(raw.get("frames") or base["frames"])
    if frames > MAX_PRODUCT_FRAMES:
        frames = MAX_PRODUCT_FRAMES
    if (frames - 1) % 4 != 0:
        frames = 17
    return {
        "preset": name,
        "width": int(raw.get("width") or base["width"]),
        "height": int(raw.get("height") or base["height"]),
        "frames": frames,
        "steps": int(raw.get("steps") or base["steps"]),
        "fps": int(raw.get("fps") or base["fps"]),
        "guide": float(raw.get("guide") if raw.get("guide") is not None else base["guide"]),
        "shift": float(raw.get("shift") if raw.get("shift") is not None else base["shift"]),
        "teacache": float(
            raw.get("teacache") if raw.get("teacache") is not None else base["teacache"]
        ),
        "seed": int(raw.get("seed") or 42),
        "output_resolution": str(raw.get("output_resolution") or "native"),
    }
