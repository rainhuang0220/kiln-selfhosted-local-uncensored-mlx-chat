from __future__ import annotations

import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.main import create_app
from app.services.chat_lifecycle import ChatLifecycle, PARKED_MESSAGE
from app.services.generation_errors import GenerationCancelled, RunResult
from app.services.media import MediaService
from app.db import get_conn


class FakeLifecycle(ChatLifecycle):
    def __init__(self, settings):
        super().__init__(settings, park_fn=self._park, restore_fn=self._restore)
        self.parks = 0
        self.restores = 0
        self.fail_restore = False

    async def _park(self, settings):
        self.parks += 1

    async def _restore(self, settings):
        self.restores += 1
        if self.fail_restore:
            raise RuntimeError("restore failed")


@pytest.fixture
def media_app(tmp_settings, chat_service, tmp_path: Path):
    async def fake_runner(spec):
        out = Path(tmp_settings.generations_dir) / (
            f"{spec['id']}.png" if spec["kind"] == "image" else f"{spec['id']}.mp4"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-bytes")
        return RunResult(output_path=str(out), metrics={"wall_s": 0.01, "backend": spec["backend"]})

    tmp_settings.generations_dir = str(tmp_path / "generations")
    tmp_settings.pause_chat_for_video = False
    life = FakeLifecycle(tmp_settings)
    svc = MediaService(tmp_settings, runner=fake_runner, lifecycle=life)
    app = create_app(tmp_settings, chat=chat_service, media=svc)
    app.state.fake_life = life
    return app


def _wait_status(c, job_id, terminal=("done", "failed", "cancelled", "interrupted"), n=80):
    got = {}
    for _ in range(n):
        got = c.get(f"/generate/{job_id}").json()
        if got.get("status") in terminal:
            return got
        time.sleep(0.05)
    return got


def test_generate_image_job(media_app):
    with TestClient(media_app) as c:
        r = c.post(
            "/generate",
            json={"kind": "image", "prompt": "a red kiln", "width": 512, "height": 512, "seed": 1},
        )
        assert r.status_code == 200, r.text
        job = r.json()
        assert job["kind"] == "image"
        got = _wait_status(c, job["id"])
        assert got["status"] == "done", got
        assert got["output_url"] == f"/generate/{job['id']}/file"
        file_r = c.get(f"/generate/{job['id']}/file")
        assert file_r.status_code == 200
        assert file_r.content == b"fake-bytes"


def test_generate_rejects_empty_prompt(media_app):
    with TestClient(media_app) as c:
        r = c.post("/generate", json={"kind": "image", "prompt": "  "})
        assert r.status_code in {400, 422}


def test_generate_backends(media_app):
    with TestClient(media_app) as c:
        r = c.get("/generate/backends")
        assert r.status_code == 200
        body = r.json()
        ids = {x["id"] for x in body["image"]}
        assert "flux2-klein-4b" in ids
        assert "z-image-turbo" in ids
        video_ids = {x["id"] for x in body["video"]}
        assert "nsfw-wan-1.3b" in video_ids
        zimg = next(x for x in body["image"] if x["id"] == "z-image-turbo")
        flux = next(x for x in body["image"] if x["id"] == "flux2-klein-4b")
        assert zimg["default"] is True
        assert flux["default"] is False
        presets = {p["id"] for p in body["video_presets"]}
        assert presets == {"fast", "standard", "long"}
        std = next(p for p in body["video_presets"] if p["id"] == "standard")
        assert std["recommended"] is True
        assert std["steps"] == 10
        assert std["frames"] == 17


def test_health_and_chat_during_slow_generation(tmp_settings, chat_service, tmp_path: Path):
    import asyncio
    import threading

    started = threading.Event()
    release = threading.Event()

    async def slow_runner(spec):
        started.set()
        await asyncio.to_thread(release.wait, 5)
        out = Path(tmp_settings.generations_dir) / f"{spec['id']}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-bytes")
        return RunResult(output_path=str(out), metrics={"wall_s": 0.4, "backend": spec["backend"]})

    tmp_settings.generations_dir = str(tmp_path / "generations")
    tmp_settings.pause_chat_for_video = False
    svc = MediaService(tmp_settings, runner=slow_runner, lifecycle=FakeLifecycle(tmp_settings))
    app = create_app(tmp_settings, chat=chat_service, media=svc)
    with TestClient(app) as c:
        r = c.post("/generate", json={"kind": "video", "prompt": "a kiln", "frames": 17, "seed": 1})
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]
        assert started.wait(2)
        health = c.get("/health")
        assert health.status_code == 200
        chat = c.post("/chat", json={"message": "ping", "stream": False})
        assert chat.status_code == 200, chat.text
        release.set()
        got = _wait_status(c, job_id)
        assert got["status"] == "done", got


def test_chat_parked_returns_503(tmp_settings, chat_service, tmp_path: Path):
    import asyncio
    import threading

    started = threading.Event()
    release = threading.Event()
    life = FakeLifecycle(tmp_settings)

    async def slow_runner(spec):
        started.set()
        await asyncio.to_thread(release.wait, 5)
        out = Path(tmp_settings.generations_dir) / f"{spec['id']}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake")
        return RunResult(output_path=str(out), metrics={"wall_s": 0.2, "backend": spec["backend"]})

    tmp_settings.generations_dir = str(tmp_path / "g")
    tmp_settings.pause_chat_for_video = True
    svc = MediaService(tmp_settings, runner=slow_runner, lifecycle=life)
    app = create_app(tmp_settings, chat=chat_service, media=svc)
    with TestClient(app) as c:
        r = c.post("/generate", json={"kind": "video", "prompt": "a kiln", "preset": "standard"})
        assert r.status_code == 200
        assert started.wait(2)
        time.sleep(0.05)
        chat = c.post("/chat", json={"message": "ping", "stream": False})
        assert chat.status_code == 503, chat.text
        body = chat.json()
        assert body["code"] == "CHAT_MODEL_PARKED"
        assert body["retryable"] is True
        assert PARKED_MESSAGE in body["message"]
        health = c.get("/health").json()
        assert health["chat"]["state"] in {"parking", "parked", "restoring"}
        release.set()
        got = _wait_status(c, r.json()["id"])
        assert got["status"] == "done", got
        assert life.parks == 1
        assert life.restores >= 1
        chat2 = c.post("/chat", json={"message": "ping", "stream": False})
        assert chat2.status_code == 200, chat2.text


def test_video_failure_restores_chat(tmp_settings, chat_service, tmp_path: Path):
    life = FakeLifecycle(tmp_settings)

    async def boom(spec):
        raise RuntimeError("ffmpeg exploded")

    tmp_settings.generations_dir = str(tmp_path / "g")
    tmp_settings.pause_chat_for_video = True
    svc = MediaService(tmp_settings, runner=boom, lifecycle=life)
    app = create_app(tmp_settings, chat=chat_service, media=svc)
    with TestClient(app) as c:
        r = c.post("/generate", json={"kind": "video", "prompt": "a kiln"})
        got = _wait_status(c, r.json()["id"])
        assert got["status"] == "failed"
        assert life.parks == 1
        assert life.restores >= 1
        chat = c.post("/chat", json={"message": "ping", "stream": False})
        assert chat.status_code == 200


def test_cancel_queued_and_running(tmp_settings, chat_service, tmp_path: Path):
    import asyncio
    import threading

    started = threading.Event()
    release = threading.Event()
    life = FakeLifecycle(tmp_settings)

    async def slow_runner(spec):
        started.set()
        cancel = spec.get("cancel")
        for _ in range(80):
            if cancel is not None and cancel.is_set():
                raise GenerationCancelled()
            if release.is_set():
                break
            await asyncio.sleep(0.05)
        if cancel is not None and cancel.is_set():
            raise GenerationCancelled()
        out = Path(tmp_settings.generations_dir) / f"{spec['id']}.mp4"
        out.write_bytes(b"x")
        return RunResult(output_path=str(out), metrics={})

    tmp_settings.generations_dir = str(tmp_path / "g")
    tmp_settings.pause_chat_for_video = True
    svc = MediaService(tmp_settings, runner=slow_runner, lifecycle=life)
    app = create_app(tmp_settings, chat=chat_service, media=svc)
    with TestClient(app) as c:
        a = c.post("/generate", json={"kind": "video", "prompt": "one"}).json()
        b = c.post("/generate", json={"kind": "video", "prompt": "two"}).json()
        assert started.wait(2)
        queued = c.get(f"/generate/{b['id']}").json()
        assert queued["status"] == "queued"
        cancel_b = c.post(f"/generate/{b['id']}/cancel")
        assert cancel_b.status_code == 200
        assert cancel_b.json()["status"] == "cancelled"
        cancel_a = c.post(f"/generate/{a['id']}/cancel")
        assert cancel_a.status_code == 200
        got = _wait_status(c, a["id"])
        assert got["status"] == "cancelled", got
        assert life.restores >= 1
        chat = c.post("/chat", json={"message": "ping", "stream": False})
        assert chat.status_code == 200


def test_stale_jobs_marked_interrupted(tmp_settings, chat_service, tmp_path: Path):
    tmp_settings.generations_dir = str(tmp_path / "g")
    Path(tmp_settings.generations_dir).mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    now = int(time.time() * 1000)
    conn.execute(
        """
        INSERT INTO media_jobs(
          id, user_id, kind, backend, status, prompt, params_json,
          created_at, updated_at, started_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        ("stale-1", None, "video", "nsfw-wan-1.3b", "generating", "x", "{}", now, now, now),
    )
    conn.commit()
    svc = MediaService(tmp_settings, lifecycle=FakeLifecycle(tmp_settings))
    svc.recover_stale()
    job = svc.get("stale-1", None)
    assert job is not None
    assert job["status"] == "interrupted"


def test_heavy_generation_is_serial(tmp_settings, chat_service, tmp_path: Path):
    import asyncio
    import threading

    current = {"n": 0, "max": 0}
    lock = threading.Lock()
    release = threading.Event()

    async def runner(spec):
        with lock:
            current["n"] += 1
            current["max"] = max(current["max"], current["n"])
        await asyncio.to_thread(release.wait, 3)
        with lock:
            current["n"] -= 1
        out = Path(tmp_settings.generations_dir) / f"{spec['id']}.png"
        out.write_bytes(b"x")
        return RunResult(output_path=str(out), metrics={})

    tmp_settings.generations_dir = str(tmp_path / "g")
    tmp_settings.pause_chat_for_video = False
    svc = MediaService(tmp_settings, runner=runner, lifecycle=FakeLifecycle(tmp_settings))
    app = create_app(tmp_settings, chat=chat_service, media=svc)
    with TestClient(app) as c:
        a = c.post("/generate", json={"kind": "image", "prompt": "one"}).json()
        b = c.post("/generate", json={"kind": "image", "prompt": "two"}).json()
        time.sleep(0.15)
        assert current["max"] == 1
        release.set()
        assert _wait_status(c, a["id"])["status"] == "done"
        assert _wait_status(c, b["id"])["status"] == "done"
        assert current["max"] == 1
