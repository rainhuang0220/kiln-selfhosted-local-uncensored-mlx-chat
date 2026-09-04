#!/usr/bin/env python3
"""Profile Wan 1.3B MLX generation on this Mac. Does not touch chat weights."""
from __future__ import annotations

import argparse
import gc
import json
import os
import resource
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT.parent
WAN_MLX = MODELS / "video-nsfw-wan-1.3b-mlx"
OUT_DIR = ROOT / "data" / "generations" / "video-bench"
BENCH_DIR = ROOT / "benchmarks" / "video"
MEDIA_PY = MODELS / ".media-venv" / "bin" / "python"
sys.path.insert(0, str(ROOT / "backend"))

BASE_PROMPT = "a copper kiln steaming in a workshop, slow camera push-in, cinematic light"
PROBE_PROMPT = os.environ.get("WAN_CONTENT_FILTER_PROBE", "")
SEED = 42
WIDTH = 832
HEIGHT = 480
FRAMES = 17
STEPS = 10
FPS = 16


def _pause_chat() -> None:
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/com.kiln.mlx"], check=False, capture_output=True)
    for _ in range(20):
        p = subprocess.run(
            ["lsof", "-nP", "-iTCP:8081", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
        )
        if p.returncode != 0 or not p.stdout.strip():
            return
        time.sleep(0.3)


def _restore_chat() -> None:
    uid = os.getuid()
    plist = Path.home() / "Library" / "LaunchAgents" / "com.kiln.mlx.plist"
    label = f"gui/{uid}/com.kiln.mlx"
    subprocess.run(["launchctl", "bootout", label], check=False, capture_output=True)
    if plist.is_file():
        subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist)], check=False, capture_output=True)
    subprocess.run(["launchctl", "kickstart", "-k", label], check=False, capture_output=True)
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            import urllib.request

            with urllib.request.urlopen("http://127.0.0.1:8081/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(1.2)
    raise RuntimeError("Hauhau 9B did not return after wan_bench")


def _patch_t5(dtype: str) -> None:
    import mlx.core as mx
    import mlx_video.models.wan_2.utils as u

    orig = u.load_t5_encoder

    def load_t5(model_path, config):
        t0 = time.perf_counter()
        from mlx_video.models.wan_2.text_encoder import T5Encoder

        encoder = T5Encoder(
            vocab_size=config.t5_vocab_size,
            dim=config.t5_dim,
            dim_attn=config.t5_dim_attn,
            dim_ffn=config.t5_dim_ffn,
            num_heads=config.t5_num_heads,
            num_layers=config.t5_num_layers,
            num_buckets=config.t5_num_buckets,
            shared_pos=False,
        )
        t_alloc = time.perf_counter()
        weights = mx.load(str(model_path))
        t_load = time.perf_counter()
        if dtype == "float32":
            weights = {k: v.astype(mx.float32) for k, v in weights.items()}
        t_cast = time.perf_counter()
        encoder.load_weights(list(weights.items()))
        mx.eval(encoder.parameters())
        t_eval = time.perf_counter()
        load_t5.last_times = {
            "t5_alloc_s": round(t_alloc - t0, 3),
            "t5_mx_load_s": round(t_load - t_alloc, 3),
            "t5_cast_s": round(t_cast - t_load, 3),
            "t5_eval_s": round(t_eval - t_cast, 3),
            "t5_load_total_s": round(t_eval - t0, 3),
            "t5_dtype": dtype,
        }
        return encoder

    load_t5.last_times = {}
    u.load_t5_encoder = load_t5
    import mlx_video.models.wan_2.generate as g

    g.load_t5_encoder = load_t5
    return load_t5


def _swap_used_gb() -> float:
    import re

    out = subprocess.check_output(["sysctl", "-n", "vm.swapusage"], text=True)
    m = re.search(r"used = ([\d.]+)M", out)
    return round(float(m.group(1)) / 1024.0, 3) if m else 0.0


def _mem() -> dict:
    import mlx.core as mx

    ru = resource.getrusage(resource.RUSAGE_SELF)
    rss = ru.ru_maxrss
    return {
        "rss_gb": round(rss / 1024**3, 3),
        "mlx_peak_gb": round(mx.get_peak_memory() / 1024**3, 3),
        "mlx_cache_gb": round(mx.get_cache_memory() / 1024**3, 3),
        "swap_used_gb": _swap_used_gb(),
    }


def _start_swap_guard(delta_gb: float, start_used: float) -> threading.Event:
    import threading

    stop = threading.Event()
    if delta_gb <= 0:
        return stop

    def watch() -> None:
        while not stop.wait(5.0):
            used = _swap_used_gb()
            if used - start_used >= delta_gb:
                print(
                    f"SWAP_ABORT used={used}GB start={start_used}GB delta_limit={delta_gb}GB",
                    flush=True,
                )
                os.kill(os.getpid(), signal.SIGTERM)
                return

    threading.Thread(target=watch, daemon=True).start()
    return stop


def run_one(args: argparse.Namespace) -> dict:
    os.environ.setdefault(
        "WAN_T5_TOKENIZER",
        str(MODELS / "video-wan21-t2v-1.3b-aux" / "google" / "umt5-xxl"),
    )
    import mlx.core as mx
    from mlx_video.models.wan_2.generate import generate_video

    t5_loader = _patch_t5(args.t5_dtype)
    tea = None
    no_compile = args.no_compile
    if args.teacache and args.teacache > 0:
        from app.services.wan_teacache import install_teacache

        tea = install_teacache(thresh=args.teacache, steps=args.steps, use_ret=args.teacache_ret)
        no_compile = True
    mx.reset_peak_memory()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = args.name.replace(" ", "_")
    out = OUT_DIR / f"{tag}.mp4"
    swap0 = _swap_used_gb()
    guard = _start_swap_guard(args.abort_swap_gb, swap0)
    t0 = time.perf_counter()
    try:
        generate_video(
            model_dir=str(WAN_MLX),
            prompt=args.prompt,
            negative_prompt="" if args.no_negative else None,
            width=args.width,
            height=args.height,
            num_frames=args.frames,
            steps=args.steps,
            guide_scale=args.guide,
            seed=args.seed,
            output_path=str(out),
            scheduler=args.scheduler,
            tiling=args.tiling,
            no_compile=no_compile,
        )
    finally:
        guard.set()
    wall = time.perf_counter() - t0
    rec = {
        "name": args.name,
        "prompt": args.prompt,
        "seed": args.seed,
        "width": args.width,
        "height": args.height,
        "frames": args.frames,
        "steps": args.steps,
        "guide": args.guide,
        "scheduler": args.scheduler,
        "tiling": args.tiling,
        "compile": not no_compile,
        "no_negative": args.no_negative,
        "wall_s": round(wall, 3),
        "output": str(out),
        "bytes": out.stat().st_size if out.is_file() else 0,
        "swap_start_gb": swap0,
        **(getattr(t5_loader, "last_times", {}) or {}),
        **_mem(),
    }
    if tea is not None:
        rec["teacache"] = tea.as_dict()
    return rec


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--name", default="run")
    p.add_argument("--prompt", default=BASE_PROMPT)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--width", type=int, default=WIDTH)
    p.add_argument("--height", type=int, default=HEIGHT)
    p.add_argument("--frames", type=int, default=FRAMES)
    p.add_argument("--steps", type=int, default=STEPS)
    p.add_argument("--guide", type=float, default=5.0)
    p.add_argument("--scheduler", default="unipc")
    p.add_argument("--tiling", default="auto")
    p.add_argument("--t5-dtype", default="float32", choices=["float32", "bfloat16"])
    p.add_argument("--no-compile", action="store_true")
    p.add_argument("--no-negative", action="store_true")
    p.add_argument("--no-pause", action="store_true")
    p.add_argument("--teacache", type=float, default=0.0)
    p.add_argument("--teacache-ret", action="store_true")
    p.add_argument("--abort-swap-gb", type=float, default=0.0)
    p.add_argument("--repeat", type=int, default=1)
    args = p.parse_args()
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    paused = False

    def _on_term(signum, frame):
        raise SystemExit(2)

    signal.signal(signal.SIGTERM, _on_term)
    try:
        if not args.no_pause:
            _pause_chat()
            paused = True
        rows = []
        for i in range(args.repeat):
            args.name = f"{args.name}" if args.repeat == 1 else f"{args.name}-r{i+1}"
            rec = run_one(args)
            rows.append(rec)
            print(json.dumps(rec, ensure_ascii=False, indent=2))
            gc.collect()
        path = BENCH_DIR / f"{rows[0]['name'].split('-r')[0]}.json"
        path.write_text(json.dumps(rows if len(rows) > 1 else rows[0], indent=2))
        print("wrote", path)
    except SystemExit as exc:
        rec = {
            "name": args.name,
            "aborted": True,
            "reason": "swap_guard" if args.abort_swap_gb else "signal",
            "frames": args.frames,
            "width": args.width,
            "height": args.height,
            "steps": args.steps,
            "swap_used_gb": _swap_used_gb(),
            "exit": exc.code,
        }
        path = BENCH_DIR / f"{args.name}.json"
        path.write_text(json.dumps(rec, indent=2))
        print("wrote", path)
        raise
    finally:
        if paused:
            _restore_chat()
            print("HEALTH_RESTORED")


if __name__ == "__main__":
    if sys.executable != str(MEDIA_PY) and MEDIA_PY.is_file():
        os.execv(str(MEDIA_PY), [str(MEDIA_PY), *sys.argv])
    main()
