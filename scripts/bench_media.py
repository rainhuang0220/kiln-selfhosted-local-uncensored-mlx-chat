#!/usr/bin/env python3
"""Local image/video wall-clock bench. Does not touch Hauhau 9B weights."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--kind", choices=["image", "video"], required=True)
    p.add_argument("--backend", default="")
    p.add_argument("--prompt", default="a copper kiln in a workshop, cinematic light")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--width", type=int, default=0)
    p.add_argument("--height", type=int, default=0)
    p.add_argument("--steps", type=int, default=0)
    args = p.parse_args()
    import sys

    sys.path.insert(0, str(ROOT / "kiln" / "backend"))
    from app.config import Settings
    from app.services.media_runtime import run_generation

    settings = Settings()
    spec = {
        "id": f"bench-{int(time.time())}",
        "kind": args.kind,
        "backend": args.backend
        or (settings.default_image_backend if args.kind == "image" else settings.default_video_backend),
        "prompt": args.prompt,
        "params": {
            k: v
            for k, v in {
                "width": args.width or None,
                "height": args.height or None,
                "steps": args.steps or None,
                "seed": args.seed,
            }.items()
            if v is not None
        },
    }
    t0 = time.perf_counter()
    result = run_generation(settings, spec)
    print(json.dumps({"result": result.metrics, "path": result.output_path, "wall_s": time.perf_counter() - t0}, indent=2))


if __name__ == "__main__":
    main()
