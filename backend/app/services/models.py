from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from huggingface_hub import HfApi, snapshot_download

from app.config import Settings

logger = logging.getLogger(__name__)


class ModelManager:
    """Keeps the UI's model inventory separate from filesystem details."""

    def __init__(
        self,
        settings: Settings,
        hub: HfApi | None = None,
        on_activated: Callable[[], None] | None = None,
    ):
        self.settings = settings
        self.hub = hub or HfApi()
        self.jobs: dict[str, dict[str, object]] = {}
        self.on_activated = on_activated

    @staticmethod
    def restore_active_selection(settings: Settings) -> None:
        """Load a locally selected model without exposing its path to clients."""
        state = Path(settings.model_selection_state_path).expanduser()
        try:
            record = json.loads(state.read_text(encoding="utf-8"))
            model_id = str(record["id"])
            path = Path(str(record["path"])).expanduser().resolve()
            library = Path(settings.model_library_path).expanduser().resolve()
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            return
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", model_id)
            or library not in path.parents
            or not (path / "config.json").is_file()
        ):
            return
        settings.model_name = model_id
        settings.model_path = str(path)

    def list_local(self) -> dict[str, object]:
        model_id = self.settings.model_name
        data: list[dict[str, object]] = [
            {
                "id": model_id,
                "name": model_id,
                "source": "configured",
                "status": "active",
            }
        ]
        root = Path(self.settings.model_library_path).expanduser()
        if root.is_dir():
            for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
                if not path.is_dir() or path.name.startswith(".") or path.name == model_id:
                    continue
                metadata_path = path / "kiln-model.json"
                if not metadata_path.is_file() and not (path / "config.json").is_file():
                    continue
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
                except (OSError, json.JSONDecodeError):
                    metadata = {}
                record: dict[str, object] = {
                    "id": path.name,
                    "name": str(metadata.get("name") or path.name.rsplit("--", 1)[-1]),
                    "source": "huggingface" if metadata.get("repo_id") else "local",
                    "status": "ready",
                }
                if isinstance(metadata.get("repo_id"), str):
                    record["repo_id"] = metadata["repo_id"]
                if isinstance(metadata.get("revision"), str):
                    record["revision"] = metadata["revision"]
                data.append(record)
        return {
            "active_id": model_id,
            "data": data,
        }

    def search_catalog(self, query: str, limit: int, mlx_only: bool) -> dict[str, object]:
        entries: list[dict[str, Any]] = []
        for item in self.hub.list_models(
            search=query or None,
            sort="downloads",
            limit=limit * (3 if mlx_only else 1),
            full=True,
        ):
            model_id = str(getattr(item, "id", ""))
            tags = [str(tag) for tag in (getattr(item, "tags", None) or [])]
            is_mlx = "mlx" in model_id.lower() or any("mlx" in tag.lower() for tag in tags)
            if mlx_only and not is_mlx:
                continue
            updated = getattr(item, "last_modified", None)
            entries.append(
                {
                    "id": model_id,
                    "name": model_id.rsplit("/", 1)[-1],
                    "downloads": int(getattr(item, "downloads", 0) or 0),
                    "likes": int(getattr(item, "likes", 0) or 0),
                    "updated_at": updated.isoformat() if updated else None,
                    "pipeline_tag": getattr(item, "pipeline_tag", None),
                    "tags": tags[:16],
                    "mlx_compatible": is_mlx,
                }
            )
            if len(entries) >= limit:
                break
        return {"query": query, "source": "huggingface", "data": entries}

    def validate_hub_model(self, repo_id: str, revision: str | None = None) -> None:
        """Verify the exact Hub revision before its download task is admitted."""
        if not self.settings.model_downloads_enabled:
            raise RuntimeError("model downloads are disabled on this host")
        info = self.hub.model_info(repo_id, revision=revision)
        tags = [str(tag).lower() for tag in (getattr(info, "tags", None) or [])]
        if "mlx" not in repo_id.lower() and not any("mlx" in tag for tag in tags):
            raise ValueError("model is not MLX-ready; choose an MLX conversion")
        filenames = {
            str(getattr(sibling, "rfilename", ""))
            for sibling in (getattr(info, "siblings", None) or [])
        }
        if "config.json" not in filenames or not any(name.endswith(".safetensors") for name in filenames):
            raise ValueError("model revision does not contain MLX weight files")

    async def queue_download(
        self, repo_id: str, revision: str | None = None, activate: bool = False
    ) -> dict[str, object]:
        await asyncio.to_thread(self.validate_hub_model, repo_id, revision)
        job_id = str(uuid.uuid4())
        job: dict[str, object] = {
            "id": job_id,
            "repo_id": repo_id,
            "revision": revision,
            "status": "queued",
            "activate": activate,
            "created_at": int(time.time() * 1000),
        }
        self.jobs[job_id] = job
        asyncio.create_task(self._download(job_id))
        return dict(job)

    def list_jobs(self) -> dict[str, object]:
        return {"data": list(self.jobs.values())}

    async def _download(self, job_id: str) -> None:
        job = self.jobs[job_id]
        job["status"] = "downloading"
        repo_id = str(job["repo_id"])
        revision = job.get("revision") or None
        destination = Path(self.settings.model_library_path).expanduser() / repo_id.replace("/", "--")
        try:
            await asyncio.to_thread(
                snapshot_download,
                repo_id=repo_id,
                revision=str(revision) if revision else None,
                local_dir=destination,
            )
            metadata = {
                "repo_id": repo_id,
                "revision": revision or "main",
                "downloaded_at": int(time.time() * 1000),
            }
            (destination / "kiln-model.json").write_text(
                json.dumps(metadata, ensure_ascii=False, sort_keys=True), encoding="utf-8"
            )
            job["model_id"] = destination.name
            if bool(job.get("activate")):
                result = await asyncio.to_thread(self.activate, destination.name)
                job["status"] = str(result["status"])
            else:
                job["status"] = "ready"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Model download failed for %s", repo_id)
            job["status"] = "error"
            job["error"] = "Download failed. Check server logs and available disk space."

    def _path_for_model(self, model_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", model_id):
            raise ValueError("model not installed")
        if model_id == self.settings.model_name and self.settings.model_path:
            path = Path(self.settings.model_path).expanduser()
        else:
            path = Path(self.settings.model_library_path).expanduser() / model_id
        if not path.is_dir() or not (path / "config.json").is_file():
            raise ValueError("model not installed")
        return path.resolve()

    def activate(self, model_id: str) -> dict[str, object]:
        path = self._path_for_model(model_id)
        if not self.settings.model_switch_enabled:
            raise RuntimeError("model switching is disabled on this host")
        script = Path(self.settings.model_switch_script)
        if not script.is_file():
            raise RuntimeError("model switch script is missing")
        subprocess.run(
            [str(script), str(path), model_id],
            check=True,
            timeout=30,
            capture_output=True,
            text=True,
        )
        self.settings.model_path = str(path)
        self.settings.model_name = model_id
        self._save_active_selection(path, model_id)
        if self.on_activated is not None:
            self.on_activated()
        return {"id": model_id, "status": "restarting"}

    def _save_active_selection(self, path: Path, model_id: str) -> None:
        state = Path(self.settings.model_selection_state_path).expanduser()
        state.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="active-model-", suffix=".json", dir=state.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"id": model_id, "path": str(path)}, handle, sort_keys=True)
            os.chmod(temp_name, 0o600)
            Path(temp_name).replace(state)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise
