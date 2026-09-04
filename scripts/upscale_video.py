#!/usr/bin/env python3
"""480p → 720p local upscale. No extra checkpoints; ffmpeg lanczos/zscale only."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path


def upscale(src: Path, dst: Path, width: int = 1280, height: int = 720) -> dict:
    if not src.is_file():
        raise FileNotFoundError(src)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not on PATH")
    dst.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-vf",
        f"scale={width}:{height}:flags=lanczos",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "slow",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not dst.is_file():
        raise RuntimeError(proc.stderr or proc.stdout or "ffmpeg upscale failed")
    return {
        "src": str(src),
        "dst": str(dst),
        "width": width,
        "height": height,
        "wall_s": round(time.perf_counter() - t0, 3),
        "bytes": dst.stat().st_size,
        "method": "ffmpeg-lanczos",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True)
    p.add_argument("--dst", required=True)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    a = p.parse_args()
    rec = upscale(Path(a.src), Path(a.dst), a.width, a.height)
    print(json.dumps(rec, indent=2))


if __name__ == "__main__":
    main()
