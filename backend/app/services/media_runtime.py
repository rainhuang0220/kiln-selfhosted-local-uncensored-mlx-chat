from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from app.config import Settings
from app.services.generation_errors import GenerationCancelled, RunResult
from app.services import video_presets as vp

UID = os.getuid()


def _run(
    cmd: list[str],
    cwd: str | None = None,
    timeout: int = 3600,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=merged,
    )


def _port_open(port: int) -> bool:
    probe = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0 and bool(probe.stdout.strip())


def pause_mlx(settings: Settings) -> None:
    label = settings.mlx_launch_label.format(uid=UID)
    subprocess.run(["launchctl", "bootout", label], check=False, capture_output=True)
    deadline = time.time() + 30
    while time.time() < deadline:
        if not _port_open(8081):
            return
        time.sleep(0.4)
    raise RuntimeError("chat worker did not release :8081 while parking")


def _health_ok(url: str) -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def _smoke_chat(settings: Settings) -> bool:
    import json
    import urllib.request

    body = json.dumps(
        {
            "model": settings.model_name,
            "messages": [{"role": "user", "content": "ok"}],
            "max_tokens": 1,
            "stream": False,
        }
    ).encode()
    req = urllib.request.Request(
        settings.mlx_chat_url(),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def restore_mlx(settings: Settings) -> None:
    label = settings.mlx_launch_label.format(uid=UID)
    plist = settings.mlx_plist
    domain = f"gui/{UID}"
    subprocess.run(["launchctl", "bootout", label], check=False, capture_output=True)
    if Path(plist).is_file():
        subprocess.run(["launchctl", "bootstrap", domain, plist], check=False, capture_output=True)
    subprocess.run(["launchctl", "kickstart", "-k", label], check=False, capture_output=True)
    deadline = time.time() + 180
    while time.time() < deadline:
        if _health_ok(settings.mlx_health_url()):
            if _smoke_chat(settings):
                return
            # Model is up; a one-token completion can still race during load.
            time.sleep(1.5)
            if _health_ok(settings.mlx_health_url()):
                return
        time.sleep(1.5)
    raise RuntimeError("chat worker did not become healthy on :8081 after restore")


def _run_cancellable(
    cmd: list[str],
    *,
    timeout: int,
    env: dict[str, str] | None,
    cancel: threading.Event | None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=merged,
    )
    t0 = time.time()
    try:
        while True:
            if cancel is not None and cancel.is_set():
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=25)
                except subprocess.TimeoutExpired:
                    proc.send_signal(signal.SIGINT)
                    try:
                        proc.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                raise GenerationCancelled()
            rc = proc.poll()
            if rc is not None:
                stdout, stderr = proc.communicate()
                return subprocess.CompletedProcess(cmd, rc, stdout, stderr)
            if time.time() - t0 > timeout:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise TimeoutError("generation timed out")
            time.sleep(0.4)
    except GenerationCancelled:
        raise
    except Exception:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
        raise


def run_generation(settings: Settings, spec: dict[str, Any]) -> RunResult:
    kind = spec["kind"]
    if kind == "image":
        return _run_image(settings, spec)
    if kind == "video":
        return _run_video(settings, spec)
    raise ValueError(f"unknown kind {kind}")


def _run_image(settings: Settings, spec: dict[str, Any]) -> RunResult:
    backend = spec["backend"]
    params = spec.get("params") or {}
    width = int(params.get("width") or 1024)
    height = int(params.get("height") or 1024)
    seed = int(params.get("seed") or 42)
    out_dir = Path(settings.generations_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{spec['id']}.png"
    py = settings.media_python
    t0 = time.perf_counter()
    if backend == "flux2-klein-4b":
        steps = int(params.get("steps") or 4)
        model = settings.image_flux_dir
        cmd = [
            py, "-m", "mflux.cmd",
        ]
        # Prefer the published CLI if present.
        cli = shutil.which("mflux-generate-flux2", path=str(Path(py).parent))
        if cli:
            cmd = [
                cli,
                "--model", model,
                "--prompt", spec["prompt"],
                "--width", str(width),
                "--height", str(height),
                "--steps", str(steps),
                "--seed", str(seed),
                "--output", str(out),
                "--low-ram",
                "--vae-tiling",
            ]
        else:
            cmd = [
                py, "-c",
                (
                    "from mflux.models.flux2.variants import Flux2Klein\n"
                    "from mflux.models.common.config import ModelConfig\n"
                    "import sys\n"
                    "model=Flux2Klein(model_config=ModelConfig.flux2_klein_4b(), "
                    "local_path=sys.argv[1] if False else None)\n"
                ),
            ]
            raise RuntimeError("mflux-generate-flux2 not installed in media venv")
    elif backend == "z-image-turbo":
        steps = int(params.get("steps") or 9)
        model = settings.image_zimage_dir
        cli = shutil.which("mflux-generate-z-image-turbo", path=str(Path(py).parent))
        if not cli:
            raise RuntimeError("mflux-generate-z-image-turbo not installed in media venv")
        cmd = [
            cli,
            "--model", model,
            "--prompt", spec["prompt"],
            "--width", str(width),
            "--height", str(height),
            "--steps", str(steps),
            "--seed", str(seed),
            "--output", str(out),
        ]
    else:
        raise ValueError(f"unknown image backend {backend}")
    if not Path(model).exists():
        raise RuntimeError(f"image weights missing: {model}")
    cancel = spec.get("cancel")
    proc = _run_cancellable(cmd, timeout=1800, env=None, cancel=cancel)
    if proc.returncode != 0 or not out.is_file():
        err = (proc.stderr or proc.stdout or "image generation failed")[-1500:]
        raise RuntimeError(err)
    return RunResult(
        output_path=str(out),
        metrics={
            "wall_s": round(time.perf_counter() - t0, 3),
            "width": width,
            "height": height,
            "steps": steps,
            "seed": seed,
            "backend": backend,
            "bytes": out.stat().st_size,
        },
    )


def _run_video(settings: Settings, spec: dict[str, Any]) -> RunResult:
    params = vp.resolve(spec.get("params") or {})
    width = params["width"]
    height = params["height"]
    frames = params["frames"]
    steps = params["steps"]
    seed = params["seed"]
    fps = params["fps"]
    out_dir = Path(settings.generations_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{spec['id']}.mp4"
    mlx_dir = Path(settings.video_wan_mlx_dir)
    py = settings.media_python
    if not mlx_dir.exists() or not (mlx_dir / "config.json").exists():
        _convert_wan(settings)
    if not Path(settings.video_wan_dit).is_file():
        raise RuntimeError(f"Wan DiT missing: {settings.video_wan_dit}")
    t0 = time.perf_counter()
    tok = Path(settings.video_wan_aux_dir) / "google" / "umt5-xxl"
    backend_dir = Path(__file__).resolve().parents[2]
    env = {"PYTHONPATH": str(backend_dir)}
    if tok.is_dir():
        env["WAN_T5_TOKENIZER"] = str(tok)
    cmd = [
        py, "-m", "app.services.wan_fast",
        "--model-dir", str(mlx_dir),
        "--prompt", spec["prompt"],
        "--output-path", str(out),
        "--tokenizer-dir", str(tok) if tok.is_dir() else "",
        "--width", str(width),
        "--height", str(height),
        "--num-frames", str(frames),
        "--steps", str(steps),
        "--guide-scale", str(params["guide"]),
        "--seed", str(seed),
        "--tiling", "auto",
        "--teacache", str(params["teacache"]),
    ]
    proc = _run_cancellable(cmd, timeout=7200, env=env, cancel=spec.get("cancel"))
    if proc.returncode != 0 or not out.is_file():
        err = (proc.stderr or proc.stdout or "video generation failed")[-1500:]
        raise RuntimeError(err)
    output_res = params.get("output_resolution") or "native"
    if output_res in {"720p", "1280x720"}:
        scaled = out_dir / f"{spec['id']}-720p.mp4"
        _ffmpeg_scale(out, scaled, 1280, 720)
        if scaled.is_file():
            out.unlink(missing_ok=True)
            scaled.rename(out)
            width, height = 1280, 720
    return RunResult(
        output_path=str(out),
        metrics={
            "wall_s": round(time.perf_counter() - t0, 3),
            "width": width,
            "height": height,
            "frames": frames,
            "steps": steps,
            "fps": fps,
            "seed": seed,
            "preset": params.get("preset"),
            "teacache": params["teacache"],
            "output_resolution": output_res,
            "backend": spec["backend"],
            "bytes": out.stat().st_size,
        },
    )


def _ffmpeg_scale(src: Path, dst: Path, width: int, height: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not on PATH; cannot apply 720p output scale")
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-vf", f"scale={width}:{height}:flags=lanczos",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p", "-an", str(dst),
    ]
    proc = _run(cmd, timeout=120)
    if proc.returncode != 0 or not dst.is_file():
        raise RuntimeError((proc.stderr or proc.stdout or "ffmpeg scale failed")[-800:])


def _convert_wan(settings: Settings) -> None:
    aux = Path(settings.video_wan_aux_dir)
    dit = Path(settings.video_wan_dit)
    mlx_dir = Path(settings.video_wan_mlx_dir)
    t5_src = aux / "models_t5_umt5-xxl-enc-bf16.pth"
    if not aux.exists():
        raise RuntimeError(f"Wan aux weights missing: {aux}")
    if not dit.is_file():
        raise RuntimeError(f"Wan DiT missing: {dit}")
    mlx_dir.mkdir(parents=True, exist_ok=True)
    if (
        (mlx_dir / "model.safetensors").is_file()
        and (mlx_dir / "vae.safetensors").is_file()
        and not (mlx_dir / "t5_encoder.safetensors").is_file()
    ):
        if not t5_src.is_file() or t5_src.stat().st_size < 10_000_000_000:
            raise RuntimeError(f"Wan T5 encoder missing or incomplete: {t5_src}")
        _convert_wan_t5(settings.media_python, t5_src, mlx_dir)
        return
    staging = aux.parent / "video-wan21-t2v-1.3b-nsfw-src"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(
        aux,
        staging,
        ignore=shutil.ignore_patterns(".cache", ".DS_Store"),
    )
    dest = staging / "diffusion_pytorch_model.safetensors"
    shutil.copy2(dit, dest)
    py = settings.media_python
    cmd = [
        py, "-m", "mlx_video.models.wan_2.convert",
        "--checkpoint-dir", str(staging),
        "--output-dir", str(mlx_dir),
        "--dtype", "bfloat16",
        "--quantize",
        "--bits", "4",
    ]
    proc = _run(cmd, timeout=3600)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "wan convert failed")[-1500:])
    if not (mlx_dir / "t5_encoder.safetensors").is_file() and t5_src.is_file():
        _convert_wan_t5(py, t5_src, mlx_dir)


def _convert_wan_t5(py: str, t5_src: Path, mlx_dir: Path) -> None:
    script = (
        "from pathlib import Path\n"
        "import sys\n"
        "import mlx.core as mx\n"
        "from mlx_video.models.wan_2.convert import load_torch_weights, sanitize_wan_t5_weights\n"
        "src, dst = Path(sys.argv[1]), Path(sys.argv[2])\n"
        "weights = load_torch_weights(str(src))\n"
        "weights = sanitize_wan_t5_weights(weights)\n"
        "weights = {k: v.astype(mx.bfloat16) for k, v in weights.items()}\n"
        "out = dst / 't5_encoder.safetensors'\n"
        "mx.save_safetensors(str(out), weights)\n"
        "print('t5_tensors', len(weights), 'bytes', out.stat().st_size)\n"
    )
    proc = _run([py, "-c", script, str(t5_src), str(mlx_dir)], timeout=3600)
    if proc.returncode != 0 or not (mlx_dir / "t5_encoder.safetensors").is_file():
        raise RuntimeError((proc.stderr or proc.stdout or "wan T5 convert failed")[-1500:])
