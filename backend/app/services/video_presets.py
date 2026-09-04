"""Product video generation presets. Values are this Mac's measured defaults."""
from __future__ import annotations

from typing import Any

# Training-free TeaCache threshold for Wan 1.3B (ali-vilab coefficients).
TEACACHE_THRESHOLD = 0.05
GUIDE_SCALE = 5.0
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
        "steps": 8,
        "fps": FPS,
        "guide": GUIDE_SCALE,
        "teacache": TEACACHE_THRESHOLD,
        "clip_s": 1.1,
        "typical_wall_s": 230,
        "typical_note": "Typically about 3–4 minutes on M4 24GB.",
        "hint": "Fewer denoise steps. Faster; slightly softer motion.",
        "recommended": False,
    },
    "standard": {
        "id": "standard",
        "label": "Standard",
        "width": WIDTH,
        "height": HEIGHT,
        "frames": 17,
        "steps": 10,
        "fps": FPS,
        "guide": GUIDE_SCALE,
        "teacache": TEACACHE_THRESHOLD,
        "clip_s": 1.1,
        "typical_wall_s": 210,
        "typical_note": "Typically about 3–4 minutes on M4 24GB.",
        "hint": "Default quality. T5 bfloat16 + TeaCache.",
        "recommended": True,
    },
    "long": {
        "id": "long",
        "label": "Long",
        "width": WIDTH,
        "height": HEIGHT,
        "frames": 33,
        "steps": 10,
        "fps": FPS,
        "guide": GUIDE_SCALE,
        "teacache": TEACACHE_THRESHOLD,
        "clip_s": 2.1,
        "typical_wall_s": 585,
        "typical_note": "Typically about 8–12 minutes on M4 24GB.",
        "hint": "About 2 seconds of video. Noticeably slower; chat parks for the job.",
        "recommended": False,
    },
}


def public_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": p["id"],
            "label": p["label"],
            "width": p["width"],
            "height": p["height"],
            "frames": p["frames"],
            "steps": p["steps"],
            "fps": p["fps"],
            "clip_s": p["clip_s"],
            "typical_wall_s": p["typical_wall_s"],
            "typical_note": p["typical_note"],
            "hint": p["hint"],
            "recommended": p["recommended"],
        }
        for p in PRESETS.values()
    ]


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
    out = {
        "preset": name,
        "width": int(raw.get("width") or base["width"]),
        "height": int(raw.get("height") or base["height"]),
        "frames": frames,
        "steps": int(raw.get("steps") or base["steps"]),
        "fps": int(raw.get("fps") or base["fps"]),
        "guide": float(raw.get("guide") if raw.get("guide") is not None else base["guide"]),
        "teacache": float(
            raw.get("teacache") if raw.get("teacache") is not None else base["teacache"]
        ),
        "seed": int(raw.get("seed") or 42),
        "output_resolution": str(raw.get("output_resolution") or "native"),
    }
    return out
