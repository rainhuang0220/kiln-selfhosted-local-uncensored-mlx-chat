"""Tests for POST /narrative/continue, resource pause, and recovery invariants."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app import db as dbmod
from app.config import Settings
from app.db import init_db
from app.main import create_app
from app.providers.base import ChatChunk, ChatRequest, ChatResult
from app.services.chat import ChatService
from app.services.narrative import NarrativeOrchestrator
from app.services.narrative_chars import count_visible_chars
from app.services.narrative_resources import ResourceSnapshot, should_pause_for_resources
from app.services import narrative_store as nstore
from app.services.tokens import TokenEstimator
from tests.conftest import local_http_client
from tests.test_narrative_engine import LongFakeProvider
from app.db import get_conn


def _force_incomplete(job_id: str, *, target: int = 20000, reason: str = "test_force") -> None:
    get_conn().execute(
        """
        UPDATE narrative_jobs
        SET status='paused_resource', pause_reason=?, target_visible_chars=?, updated_at=?
        WHERE job_id=?
        """,
        (reason, int(target), int(__import__("time").time() * 1000), job_id),
    )
    get_conn().commit()


def _settings(tmp_path: Path) -> Settings:
    db = tmp_path / "narr-continue.db"
    init_db(str(db))
    return Settings(
        sqlite_path=str(db),
        mlx_base_url="http://127.0.0.1:8081",
        model_path=str(Path(__file__).resolve().parents[3] / "qwen3.5-9b-hauhau-aggressive-mxfp4"),
        app_password="",
        kiln_exposure="local",
        kiln_public_origin="",
        cookie_secure=False,
    )


@pytest.fixture
def continue_env(tmp_path: Path, monkeypatch):
    # Default healthy resources so setup runs are not false-paused on a loaded host.
    monkeypatch.setattr(
        "app.services.narrative_resources.sample_resources",
        lambda: ResourceSnapshot(swap_free_mib=4096.0, swapout_pages=1, pages_free=500_000),
    )
    settings = _settings(tmp_path)
    dbmod._local.conn = dbmod._connect(settings.sqlite_path)
    provider = LongFakeProvider(chars_per_token=2.0)
    chat = ChatService(settings, provider, TokenEstimator(settings.model_path))
    app = create_app(settings, chat=chat)
    return settings, provider, chat, app


@pytest.mark.asyncio
async def test_continue_resumes_same_job_without_duplicating_body(continue_env):
    _, provider, chat, _ = continue_env
    orch = NarrativeOrchestrator(chat)
    done = None
    async for ev in orch.run(
        message="角色：阿远\n短篇起步",
        target_visible_chars=3000,
        segment_chars=1000,
        segment_max_tokens=400,
    ):
        if ev["event"] == "done":
            done = ev["data"]
    assert done is not None
    job_id = done["job_id"]
    _force_incomplete(job_id, target=20000)
    body_before = nstore.reassemble_body(job_id)
    vis_before = count_visible_chars(body_before)
    assert vis_before >= 1000

    events = []
    async for ev in orch.continue_job(
        job_id=job_id,
        owner_id=None,
        idempotency_key="cont-1",
        segment_max_tokens=400,
        max_new_segments=2,
        resource_check=False,
    ):
        events.append(ev)
    done2 = next(e for e in events if e["event"] == "done")
    body_after = done2["data"]["message"]["content"]
    assert body_after.startswith(body_before)
    assert count_visible_chars(body_after) > vis_before
    # No duplicated prefix block
    mid = len(body_before)
    assert body_after[mid : mid + 40] != body_before[:40]


@pytest.mark.asyncio
async def test_repeat_continue_same_idempotency_key_is_noop(continue_env):
    _, _, chat, _ = continue_env
    orch = NarrativeOrchestrator(chat)
    done = None
    async for ev in orch.run(
        message="角色：阿清\n续写测试",
        target_visible_chars=2500,
        segment_chars=900,
        segment_max_tokens=350,
    ):
        if ev["event"] == "done":
            done = ev["data"]
    job_id = done["job_id"]
    _force_incomplete(job_id, target=20000)
    body1 = None
    async for ev in orch.continue_job(job_id=job_id, idempotency_key="same-key", max_new_segments=1, resource_check=False):
        if ev["event"] == "done":
            body1 = ev["data"]["message"]["content"]
    body2 = None
    segs_before = len(nstore.list_segments(job_id))
    async for ev in orch.continue_job(job_id=job_id, idempotency_key="same-key", max_new_segments=1, resource_check=False):
        if ev["event"] == "done":
            body2 = ev["data"]["message"]["content"]
            assert ev["data"].get("idempotent_replay") is True
    assert body1 == body2
    assert len(nstore.list_segments(job_id)) == segs_before


@pytest.mark.asyncio
async def test_http_continue_endpoint_and_dual_client_lock(continue_env, monkeypatch):
    monkeypatch.setattr(
        "app.services.narrative_resources.sample_resources",
        lambda: ResourceSnapshot(swap_free_mib=2048.0, swapout_pages=1, pages_free=500_000),
    )
    _, _, chat, app = continue_env
    orch = NarrativeOrchestrator(chat)
    done = None
    async for ev in orch.run(
        message="角色：阿远\nHTTP续写",
        target_visible_chars=2200,
        segment_chars=800,
        segment_max_tokens=300,
    ):
        if ev["event"] == "done":
            done = ev["data"]
    job_id = done["job_id"]
    _force_incomplete(job_id, target=20000, reason="http_test")
    asst_id = done["message"]["id"]

    with local_http_client(app) as c:
        r1 = c.post(
            "/narrative/continue",
            json={
                "job_id": job_id,
                "assistant_message_id": asst_id,
                "idempotency_key": "http-1",
                "stream": False,
                "max_new_segments": 1,
                "segment_max_tokens": 300,
            },
        )
        assert r1.status_code == 200, r1.text
        body1 = r1.json()["message"]["content"]
        r2 = c.post(
            "/narrative/continue",
            json={
                "job_id": job_id,
                "assistant_message_id": asst_id,
                "idempotency_key": "http-1",
                "stream": False,
                "max_new_segments": 1,
            },
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["message"]["content"] == body1
        assert r2.json().get("idempotent_replay") is True

        # Second client with a different key while first hold would 409 if busy;
        # after completion, a new key may continue further.
        r3 = c.post(
            "/narrative/continue",
            json={
                "job_id": job_id,
                "assistant_message_id": asst_id,
                "idempotency_key": "http-2",
                "stream": False,
                "max_new_segments": 1,
            },
        )
        assert r3.status_code == 200, r3.text
        assert r3.json()["message"]["content"].startswith(body1)


def test_resource_pause_when_swap_free_low():
    snap = ResourceSnapshot(swap_free_mib=100.0, swapout_pages=1, pages_free=1000)
    decision = should_pause_for_resources(snap, min_free_mib=256.0)
    assert decision.should_pause is True
    assert decision.reason == "low_swap_free"


def test_resource_allows_continue_when_free_ok():
    snap = ResourceSnapshot(swap_free_mib=900.0, swapout_pages=1, pages_free=200000)
    decision = should_pause_for_resources(snap, min_free_mib=256.0)
    assert decision.should_pause is False


@pytest.mark.asyncio
async def test_continue_pauses_before_segment_when_resources_low(continue_env, monkeypatch):
    _, _, chat, _ = continue_env
    orch = NarrativeOrchestrator(chat)
    done = None
    async for ev in orch.run(
        message="角色：阿远\n资源暂停",
        target_visible_chars=2000,
        segment_chars=700,
        segment_max_tokens=250,
    ):
        if ev["event"] == "done":
            done = ev["data"]
    job_id = done["job_id"]
    _force_incomplete(job_id, target=20000, reason="setup")
    body_before = nstore.reassemble_body(job_id)

    def fake_snap():
        return ResourceSnapshot(swap_free_mib=50.0, swapout_pages=9, pages_free=10)

    monkeypatch.setattr("app.services.narrative_resources.sample_resources", fake_snap)
    events = []
    async for ev in orch.continue_job(job_id=job_id, idempotency_key="low-res", max_new_segments=3):
        events.append(ev)
    done2 = next(e for e in events if e["event"] == "done")
    assert done2["data"]["finish_reason"] == "resource_pause"
    assert done2["data"]["terminal_state"] == "paused_resource"
    assert nstore.reassemble_body(job_id) == body_before
    job = nstore.get_job(job_id)
    assert job["status"] == "paused_resource"


@pytest.mark.asyncio
async def test_save_failure_does_not_count_unsaved_chars(continue_env, monkeypatch):
    monkeypatch.setattr(
        "app.services.narrative_resources.sample_resources",
        lambda: ResourceSnapshot(swap_free_mib=2048.0, swapout_pages=1, pages_free=500_000),
    )
    _, _, chat, _ = continue_env
    orch = NarrativeOrchestrator(chat)
    done = None
    async for ev in orch.run(
        message="角色：阿清\n保存失败",
        target_visible_chars=1800,
        segment_chars=600,
        segment_max_tokens=200,
    ):
        if ev["event"] == "done":
            done = ev["data"]
    job_id = done["job_id"]
    _force_incomplete(job_id, target=20000, reason="setup")
    vis_before = nstore.get_job(job_id)["total_visible_chars"]
    body_before = nstore.reassemble_body(job_id)

    real_commit = nstore.commit_segment

    def boom(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("app.services.narrative_store.commit_segment", boom)
    events = []
    async for ev in orch.continue_job(
        job_id=job_id,
        idempotency_key="save-fail",
        max_new_segments=1,
        resource_check=False,
    ):
        events.append(ev)
    err = next((e for e in events if e["event"] == "done"), None)
    assert err is not None
    assert err["data"]["finish_reason"] in {"save_failed", "error"}
    # Stats only count durably committed segments
    assert nstore.get_job(job_id)["total_visible_chars"] == vis_before
    assert nstore.reassemble_body(job_id) == body_before
    monkeypatch.setattr("app.services.narrative_store.commit_segment", real_commit)


@pytest.mark.asyncio
async def test_interrupt_reasons_are_distinct(continue_env):
    _, _, chat, _ = continue_env
    orch = NarrativeOrchestrator(chat)
    done = None
    async for ev in orch.run(
        message="角色：阿远\n中断分类",
        target_visible_chars=1600,
        segment_chars=500,
        segment_max_tokens=180,
    ):
        if ev["event"] == "done":
            done = ev["data"]
    job_id = done["job_id"]
    _force_incomplete(job_id, target=20000, reason="setup")

    cancelled = {"v": False}

    async def run_then_cancel():
        events = []
        async for ev in orch.continue_job(
            job_id=job_id,
            idempotency_key="user-stop",
            max_new_segments=5,
            cancel_check=lambda: cancelled["v"],
            interrupt_kind="user_stop",
            resource_check=False,
        ):
            events.append(ev)
            if ev["event"] == "delta":
                cancelled["v"] = True
        return events

    events = await run_then_cancel()
    done2 = next(e for e in events if e["event"] == "done")
    assert done2["data"]["finish_reason"] == "user_stop"
    assert done2["data"]["terminal_state"] == "interrupted_user"


@pytest.mark.asyncio
async def test_dual_continue_second_client_gets_busy(continue_env, monkeypatch):
    monkeypatch.setattr(
        "app.services.narrative_resources.sample_resources",
        lambda: ResourceSnapshot(swap_free_mib=2048.0, swapout_pages=1, pages_free=500_000),
    )
    _, provider, chat, _ = continue_env
    orch = NarrativeOrchestrator(chat)
    done = None
    async for ev in orch.run(
        message="角色：阿远\n双端续写",
        target_visible_chars=1500,
        segment_chars=500,
        segment_max_tokens=160,
    ):
        if ev["event"] == "done":
            done = ev["data"]
    job_id = done["job_id"]
    _force_incomplete(job_id, target=50000)

    original_stream = provider.stream

    async def slow_stream(request: ChatRequest):
        async for chunk in original_stream(request):
            yield chunk
            await asyncio.sleep(0.05)

    provider.stream = slow_stream  # type: ignore[method-assign]
    results: list[str] = []

    async def client_a():
        async for ev in orch.continue_job(
            job_id=job_id, idempotency_key="a", max_new_segments=1, resource_check=False
        ):
            if ev["event"] == "error":
                results.append(ev["data"]["error"]["code"])
            elif ev["event"] == "done":
                results.append("done_a")

    async def client_b():
        await asyncio.sleep(0.01)
        async for ev in orch.continue_job(
            job_id=job_id, idempotency_key="b", max_new_segments=1, resource_check=False
        ):
            if ev["event"] == "error":
                results.append(ev["data"]["error"]["code"])
            elif ev["event"] == "done":
                results.append("done_b")

    await asyncio.gather(client_a(), client_b())
    assert "generation_busy" in results


@pytest.mark.asyncio
async def test_continue_survives_process_restart_simulation(continue_env, monkeypatch):
    """Persist job, drop in-memory service, reload from SQLite, continue same body."""
    monkeypatch.setattr(
        "app.services.narrative_resources.sample_resources",
        lambda: ResourceSnapshot(swap_free_mib=2048.0, swapout_pages=1, pages_free=500_000),
    )
    settings, _, chat, _ = continue_env
    orch = NarrativeOrchestrator(chat)
    done = None
    async for ev in orch.run(
        message="角色：阿清\n重启续写",
        target_visible_chars=1800,
        segment_chars=600,
        segment_max_tokens=200,
    ):
        if ev["event"] == "done":
            done = ev["data"]
    job_id = done["job_id"]
    _force_incomplete(job_id, target=20000)
    body_before = nstore.reassemble_body(job_id)

    # Simulate API restart: new ChatService + provider on same DB file.
    provider2 = LongFakeProvider(chars_per_token=2.0)
    chat2 = ChatService(settings, provider2, TokenEstimator(settings.model_path))
    orch2 = NarrativeOrchestrator(chat2)
    async for ev in orch2.continue_job(
        job_id=job_id, idempotency_key="after-restart", max_new_segments=1, resource_check=False
    ):
        if ev["event"] == "done":
            body_after = ev["data"]["message"]["content"]
            assert body_after.startswith(body_before)
            assert count_visible_chars(body_after) > count_visible_chars(body_before)
            segs = nstore.list_segments(job_id)
            assert [s["ordinal"] for s in segs] == list(range(len(segs)))


@pytest.mark.asyncio
async def test_sse_disconnect_marks_network_disconnect(continue_env, monkeypatch):
    monkeypatch.setattr(
        "app.services.narrative_resources.sample_resources",
        lambda: ResourceSnapshot(swap_free_mib=2048.0, swapout_pages=1, pages_free=500_000),
    )
    _, _, chat, _ = continue_env
    orch = NarrativeOrchestrator(chat)
    done = None
    async for ev in orch.run(
        message="角色：阿远\nSSE断连",
        target_visible_chars=1600,
        segment_chars=500,
        segment_max_tokens=180,
        resource_check=False,
    ):
        if ev["event"] == "done":
            done = ev["data"]
    job_id = done["job_id"]
    _force_incomplete(job_id, target=20000)
    body_before = nstore.reassemble_body(job_id)
    cancelled = {"v": False}

    events = []
    async for ev in orch.continue_job(
        job_id=job_id,
        idempotency_key="sse-drop",
        max_new_segments=5,
        cancel_check=lambda: cancelled["v"],
        interrupt_kind="network_disconnect",
        resource_check=False,
    ):
        events.append(ev)
        if ev["event"] == "delta":
            cancelled["v"] = True

    done2 = next(e for e in events if e["event"] == "done")
    assert done2["data"]["finish_reason"] == "network_disconnect"
    assert done2["data"]["terminal_state"] in {"interrupted_transport", "paused_resource"}
    # Committed body must not shrink or duplicate
    body_after = nstore.reassemble_body(job_id)
    assert body_after.startswith(body_before)
    assert body_before in body_after or body_after == body_before


@pytest.mark.asyncio
async def test_run_pauses_before_next_segment_on_low_resources(continue_env, monkeypatch):
    """Initial run must pause scheduling when free swap is insufficient (R5)."""
    calls = {"n": 0}

    def snap():
        calls["n"] += 1
        # First segment allowed; before second segment pause.
        if calls["n"] <= 1:
            return ResourceSnapshot(swap_free_mib=2048.0, swapout_pages=1, pages_free=500_000)
        return ResourceSnapshot(swap_free_mib=64.0, swapout_pages=99, pages_free=500_000)

    monkeypatch.setattr("app.services.narrative_resources.sample_resources", snap)
    _, _, chat, _ = continue_env
    orch = NarrativeOrchestrator(chat)
    done = None
    async for ev in orch.run(
        message="角色：阿清\n资源暂停起步",
        target_visible_chars=5000,
        segment_chars=800,
        segment_max_tokens=200,
        resource_check=True,
    ):
        if ev["event"] == "done":
            done = ev["data"]
    assert done is not None
    assert done["finish_reason"] == "resource_pause"
    assert done["terminal_state"] == "paused_resource"
    job = nstore.get_job(done["job_id"])
    assert job["status"] == "paused_resource"
    assert count_visible_chars(nstore.reassemble_body(done["job_id"])) < 5000
