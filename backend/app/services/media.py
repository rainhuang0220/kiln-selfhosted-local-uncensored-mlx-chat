from __future__ import annotations

import asyncio
import inspect
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.config import Settings
from app.db import get_conn
from app.services.chat_lifecycle import ChatLifecycle
from app.services.generation_errors import GenerationCancelled, RunResult
from app.services.prompt_compiler import CompiledPrompt, compile_visual_prompt
from app.services import image_presets as ip
from app.services import video_presets as vp

ACTIVE_STATUSES = (
    "queued",
    "enhancing_prompt",
    "parking_chat",
    "loading",
    "generating",
    "decoding",
    "exporting",
    "restoring_chat",
)
TERMINAL = {"done", "failed", "cancelled", "interrupted"}
IN_FLIGHT = tuple(s for s in ACTIVE_STATUSES if s != "queued")

IMAGE_BACKENDS = ("z-image-turbo", "flux1-dev", "flux2-klein-4b")
VIDEO_BACKENDS = ("nsfw-wan-1.3b",)

Runner = Callable[[dict[str, Any]], Awaitable[RunResult]]


def _now() -> int:
    return int(time.time() * 1000)


def _row(r) -> dict[str, Any]:
    params = json.loads(r["params_json"] or "{}")
    metrics = json.loads(r["metrics_json"] or "{}")
    output_url = None
    if r["output_path"] and r["status"] == "done":
        output_url = f"/generate/{r['id']}/file"
    return {
        "id": r["id"],
        "kind": r["kind"],
        "backend": r["backend"],
        "status": r["status"],
        "prompt": r["prompt"],
        "original_prompt": r["prompt"],
        "effective_prompt": params.get("effective_prompt") or r["prompt"],
        "prompt_mode": params.get("prompt_mode") or "raw",
        "params": params,
        "output_url": output_url,
        "error": r["error"],
        "metrics": metrics,
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "started_at": r["started_at"],
        "finished_at": r["finished_at"],
    }


class MediaService:
    def __init__(
        self,
        settings: Settings,
        runner: Runner | None = None,
        lifecycle: ChatLifecycle | None = None,
        compiler: Callable[..., Any] | None = None,
    ):
        self.settings = settings
        self._runner = runner
        self.lifecycle = lifecycle or ChatLifecycle(settings)
        self._compiler = compiler
        self._lock = asyncio.Lock()
        self._cancels: dict[str, threading.Event] = {}
        Path(settings.generations_dir).mkdir(parents=True, exist_ok=True)

    def backends(self) -> dict[str, Any]:
        flux = Path(self.settings.image_flux_dir)
        zimg = Path(self.settings.image_zimage_dir)
        flux1 = Path(self.settings.image_flux1_dev_dir)
        dit = Path(self.settings.video_wan_dit)
        aux = Path(self.settings.video_wan_aux_dir)
        mlx_dir = Path(self.settings.video_wan_mlx_dir)
        flux_ready = (flux / "transformer" / "0.safetensors").is_file() and (
            flux / "vae" / "0.safetensors"
        ).is_file()
        zimg_ready = all(
            (zimg / rel).is_file() and (zimg / rel).stat().st_size > 100_000_000
            for rel in (
                "text_encoder/0.safetensors",
                "transformer/0.safetensors",
                "transformer/1.safetensors",
                "vae/0.safetensors",
            )
        )
        flux1_files = list((flux1 / "transformer").glob("*.safetensors")) if (flux1 / "transformer").is_dir() else []
        flux1_vae = list((flux1 / "vae").glob("*.safetensors")) if (flux1 / "vae").is_dir() else []
        flux1_ready = bool(flux1_files) and flux1_files[0].stat().st_size > 50_000_000 and bool(flux1_vae)
        mlx_ready = all(
            (mlx_dir / name).is_file()
            for name in ("config.json", "model.safetensors", "t5_encoder.safetensors", "vae.safetensors")
        )
        src_ready = (
            dit.is_file()
            and dit.stat().st_size > 2_000_000_000
            and (aux / "Wan2.1_VAE.pth").is_file()
            and (aux / "Wan2.1_VAE.pth").stat().st_size > 500_000_000
            and (aux / "models_t5_umt5-xxl-enc-bf16.pth").is_file()
            and (aux / "models_t5_umt5-xxl-enc-bf16.pth").stat().st_size > 10_000_000_000
        )
        return {
            "image": [
                {
                    "id": "z-image-turbo",
                    "label": "Z-Image Turbo",
                    "ready": zimg_ready,
                    "default": self.settings.default_image_backend == "z-image-turbo",
                    "checkpoint": "Tongyi-MAI/Z-Image-Turbo via mflux 4-bit",
                    "application_filter": "none",
                    "checkpoint_censorship": "not_claimed",
                    "provenance": "verified_standard_upstream",
                },
                {
                    "id": "flux1-dev",
                    "label": "FLUX.1 [dev] Q4 (Quality)",
                    "ready": flux1_ready,
                    "default": self.settings.default_image_backend == "flux1-dev",
                    "checkpoint": "black-forest-labs/FLUX.1-dev via mflux 4-bit",
                    "application_filter": "none",
                    "checkpoint_censorship": "not_claimed",
                    "provenance": "verified_standard_upstream",
                    "license": "FLUX.1 [dev] Non-Commercial License",
                },
                {
                    "id": "flux2-klein-4b",
                    "label": "FLUX.2 Klein 4B (official text encoder may sanitize prompts)",
                    "ready": flux_ready,
                    "default": self.settings.default_image_backend == "flux2-klein-4b",
                    "checkpoint": "FLUX.2 Klein 4B",
                    "application_filter": "none",
                    "checkpoint_censorship": "encoder_may_sanitize",
                    "provenance": "verified_standard_upstream",
                },
            ],
            "image_presets": ip.public_presets(),
            "video": [
                {
                    "id": "nsfw-wan-1.3b",
                    "label": "Wan2.1 T2V 1.3B NSFW-finetuned (exp e14)",
                    "ready": mlx_ready or src_ready,
                    "default": True,
                    "checkpoint": "wan_1.3B_exp_e14 from Wan-AI/Wan2.1-T2V-1.3B fine-tune",
                    "application_filter": "none",
                    "checkpoint_censorship": "nsfw_finetune_claimed",
                    "provenance": "verified_finetune_card",
                }
            ],
            "video_presets": vp.public_presets(),
            "chat": self.lifecycle.snapshot(),
            "heavy_generation": "serial",
        }

    def get(self, job_id: str, owner_id: str | None) -> dict[str, Any] | None:
        conn = get_conn()
        if owner_id:
            row = conn.execute(
                "SELECT * FROM media_jobs WHERE id=? AND user_id=?",
                (job_id, owner_id),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM media_jobs WHERE id=?", (job_id,)).fetchone()
        return _row(row) if row else None

    def list_jobs(self, owner_id: str | None, limit: int = 20) -> list[dict[str, Any]]:
        conn = get_conn()
        if owner_id:
            rows = conn.execute(
                "SELECT * FROM media_jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (owner_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM media_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row(r) for r in rows]

    def output_path(self, job_id: str, owner_id: str | None) -> Path | None:
        conn = get_conn()
        if owner_id:
            row = conn.execute(
                "SELECT output_path FROM media_jobs WHERE id=? AND user_id=? AND status='done'",
                (job_id, owner_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT output_path FROM media_jobs WHERE id=? AND status='done'",
                (job_id,),
            ).fetchone()
        if not row or not row["output_path"]:
            return None
        path = Path(row["output_path"])
        root = Path(self.settings.generations_dir).resolve()
        try:
            path.resolve().relative_to(root)
        except ValueError:
            return None
        return path if path.is_file() else None

    def enqueue(
        self,
        *,
        kind: str,
        prompt: str,
        backend: str | None,
        params: dict[str, Any],
        owner_id: str | None,
    ) -> dict[str, Any]:
        if kind not in ("image", "video"):
            raise ValueError("kind must be image or video")
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("prompt is required")
        if kind == "image":
            params, backend = ip.resolve(params, backend)
            backend = backend or self.settings.default_image_backend
            if backend not in IMAGE_BACKENDS:
                raise ValueError(f"unknown image backend: {backend}")
        else:
            backend = backend or self.settings.default_video_backend
            if backend not in VIDEO_BACKENDS:
                raise ValueError(f"unknown video backend: {backend}")
            params = vp.resolve(params)
        job_id = str(uuid.uuid4())
        now = _now()
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO media_jobs(
              id, user_id, kind, backend, status, prompt, params_json,
              created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                job_id,
                owner_id,
                kind,
                backend,
                "queued",
                prompt,
                json.dumps(params, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.commit()
        return self.get(job_id, owner_id) or {"id": job_id, "status": "queued"}

    def cancel(self, job_id: str, owner_id: str | None) -> dict[str, Any] | None:
        job = self.get(job_id, owner_id)
        if job is None:
            return None
        if job["status"] in TERMINAL:
            return job
        ev = self._cancels.setdefault(job_id, threading.Event())
        ev.set()
        if job["status"] == "queued":
            self._set(
                job_id,
                status="cancelled",
                error="cancelled",
                finished_at=_now(),
            )
        return self.get(job_id, owner_id)

    def recover_stale(self) -> None:
        conn = get_conn()
        now = _now()
        conn.execute(
            f"""
            UPDATE media_jobs
            SET status='interrupted', error='worker lost on api restart',
                updated_at=?, finished_at=?
            WHERE status IN ({",".join("?" * len(IN_FLIGHT))})
            """,
            [now, now, *IN_FLIGHT],
        )
        conn.commit()

    def _set(self, job_id: str, **fields: Any) -> None:
        fields["updated_at"] = _now()
        keys = ", ".join(f"{k}=?" for k in fields)
        conn = get_conn()
        conn.execute(
            f"UPDATE media_jobs SET {keys} WHERE id=?",
            [*fields.values(), job_id],
        )
        conn.commit()

    async def _compile_prompt(self, kind: str, prompt: str, mode: str) -> CompiledPrompt:
        if self._compiler is not None:
            result = self._compiler(kind, prompt, mode)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, CompiledPrompt):
                return result
            text = str(result)
            return CompiledPrompt(original=prompt, effective=text, mode=mode, kind=kind)  # type: ignore[arg-type]
        return await asyncio.to_thread(
            compile_visual_prompt, prompt, kind, mode, None, self.settings
        )

    def _should_park(self, kind: str, backend: str | None = None) -> bool:
        if kind == "video":
            return bool(self.settings.pause_chat_for_video)
        if backend == "flux1-dev":
            return True
        return bool(self.settings.pause_chat_for_image)

    async def pump(self) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            while True:
                conn = get_conn()
                row = conn.execute(
                    "SELECT * FROM media_jobs WHERE status='queued' ORDER BY created_at ASC LIMIT 1"
                ).fetchone()
                if row is None:
                    return
                await self._run_job(_row(row))

    async def _run_job(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        kind = job["kind"]
        park = self._should_park(kind, job.get("backend"))
        parked = False
        cancel = self._cancels.setdefault(job_id, threading.Event())
        self._set(job_id, status="enhancing_prompt", started_at=_now())
        try:
            if cancel.is_set():
                raise GenerationCancelled()
            params = dict(job.get("params") or {})
            mode = str(params.get("prompt_mode") or "enhanced")
            if mode not in ("raw", "enhanced", "translate_enhance"):
                mode = "enhanced"
            compiled = await self._compile_prompt(kind, job["prompt"], mode)
            params["prompt_mode"] = compiled.mode
            params["original_prompt"] = compiled.original
            params["effective_prompt"] = compiled.effective
            params["compiler_violations"] = compiled.violations
            params["compiler_model"] = compiled.compiler_model
            catalog = self.backends().get(kind) or []
            match = next((b for b in catalog if b.get("id") == job["backend"]), None)
            if match:
                params["model"] = match.get("checkpoint") or match.get("label") or job["backend"]
            self._set(job_id, params_json=json.dumps(params, ensure_ascii=False))
            if cancel.is_set():
                raise GenerationCancelled()
            if park:
                self._set(job_id, status="parking_chat")
                await self.lifecycle.park(reason=job_id)
                parked = True
            if cancel.is_set():
                raise GenerationCancelled()
            self._set(job_id, status="generating")
            runner = self._runner or self._subprocess_runner
            result = await runner(
                {
                    "id": job_id,
                    "kind": kind,
                    "backend": job["backend"],
                    "prompt": compiled.effective,
                    "params": params,
                    "cancel": cancel,
                }
            )
            if cancel.is_set():
                self._cleanup_output(result.output_path)
                raise GenerationCancelled()
            self._set(job_id, status="exporting")
            if parked:
                self._set(job_id, status="restoring_chat")
                await self.lifecycle.restore()
                parked = False
            self._set(
                job_id,
                status="done",
                output_path=result.output_path,
                metrics_json=json.dumps(result.metrics, ensure_ascii=False),
                finished_at=_now(),
                error=None,
            )
        except GenerationCancelled:
            self._cleanup_job_files(job_id)
            self._set(
                job_id,
                status="cancelled",
                error="cancelled",
                finished_at=_now(),
            )
        except Exception as exc:  # noqa: BLE001
            self._cleanup_job_files(job_id)
            self._set(
                job_id,
                status="failed",
                error=str(exc)[:2000],
                finished_at=_now(),
            )
        finally:
            self._cancels.pop(job_id, None)
            if parked:
                try:
                    await self.lifecycle.restore()
                except Exception as exc:  # noqa: BLE001
                    conn = get_conn()
                    row = conn.execute(
                        "SELECT status FROM media_jobs WHERE id=?", (job_id,)
                    ).fetchone()
                    if row and row["status"] not in TERMINAL:
                        self._set(
                            job_id,
                            status="failed",
                            error=f"chat restore failed: {exc}"[:2000],
                            finished_at=_now(),
                        )

    async def _subprocess_runner(self, spec: dict[str, Any]) -> RunResult:
        from app.services.media_runtime import run_generation

        return await asyncio.to_thread(run_generation, self.settings, spec)

    def _cleanup_job_files(self, job_id: str) -> None:
        root = Path(self.settings.generations_dir)
        for path in root.glob(f"{job_id}*"):
            try:
                path.unlink()
            except OSError:
                pass

    def _cleanup_output(self, output_path: str | None) -> None:
        if not output_path:
            return
        path = Path(output_path)
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
