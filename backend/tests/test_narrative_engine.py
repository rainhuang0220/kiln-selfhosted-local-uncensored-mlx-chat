"""Narrative schema, prompt, continuity, and orchestrator tests."""

from __future__ import annotations

import pytest

from app.main import create_app
from app.providers.base import ChatChunk, ChatRequest, ChatResult
from app.services.chat import ChatService
from app.services.narrative import NarrativeOrchestrator
from app.services.narrative_chars import count_visible_chars
from app.services.narrative_continuity import check_segment
from app.services.narrative_prompt import build_segment_messages, export_config, import_config
from app.services.narrative_schema import (
    CharacterCardV2,
    MemoryRecord,
    SOURCE_MODEL_GENERATED,
    SOURCE_USER_DECLARED,
    StoryBible,
    build_outline,
    extract_story_bible_from_text,
)
from app.services.profiles import resolve_profile
from app.services.tokens import TokenEstimator


class LongFakeProvider:
    name = "fake"

    def __init__(self, chars_per_token: float = 1.5):
        self.chars_per_token = chars_per_token
        self.calls: list[ChatRequest] = []

    def context_window(self) -> int:
        return 262144

    def default_model(self) -> str:
        return "fake-long"

    async def health(self) -> bool:
        return True

    def _body(self, max_tokens: int) -> str:
        n = max(1, int(max_tokens * self.chars_per_token))
        # Distinct per-call material so continuity overlap checks stay quiet.
        unit = f"段{len(self.calls):03d}农事记述。"
        reps = (n // len(unit)) + 1
        return (unit * reps)[:n]

    async def complete(self, request: ChatRequest) -> ChatResult:
        self.calls.append(request)
        content = self._body(request.max_tokens)
        return ChatResult(
            id="chatcmpl-fake",
            model="fake-long",
            content=content,
            reasoning="",
            finish_reason="length",
            prompt_tokens=12,
            completion_tokens=request.max_tokens,
            cached_tokens=0,
            usage_source="upstream",
        )

    async def stream(self, request: ChatRequest):
        self.calls.append(request)
        content = self._body(request.max_tokens)
        # Emit in chunks to exercise SSE assembly.
        step = max(16, len(content) // 8)
        for i in range(0, len(content), step):
            yield ChatChunk(
                id="chatcmpl-fake",
                model="fake-long",
                delta_content=content[i : i + step],
            )
        yield ChatChunk(
            id="chatcmpl-fake",
            model="fake-long",
            finish_reason="length",
            prompt_tokens=12,
            completion_tokens=request.max_tokens,
            cached_tokens=0,
        )
        yield ChatChunk(id="chatcmpl-fake", model="fake-long", wire_done=True)


def test_long_form_profile_is_narrative_not_default():
    p = resolve_profile("long_form")
    assert p["profile"] == "long_form"
    assert p["mode"] == "narrative"
    assert p["target_visible_chars"] >= 20000
    assert p["max_tokens"] >= 2048
    assert resolve_profile("interactive_dialogue")["max_tokens"] == 1536


def test_character_card_keeps_unknown_fields():
    card = CharacterCardV2.from_dict(
        {"name": "阿远", "description": "渔人", "custom_tag": "x", "creator_notes": "private"}
    )
    assert card.name == "阿远"
    assert card.creator_notes == "private"
    assert card.extensions["unknown_fields"]["custom_tag"] == "x"


def test_model_fact_cannot_be_canonical():
    with pytest.raises(ValueError):
        MemoryRecord(
            fact="秘密",
            scope="chat",
            source_type=SOURCE_MODEL_GENERATED,
            canonical=True,
        )
    ok = MemoryRecord(
        fact="用户设定",
        scope="chat",
        source_type=SOURCE_USER_DECLARED,
        canonical=True,
    )
    assert ok.canonical is True


def test_outline_covers_target():
    plan = build_outline(target_visible_chars=20000, segment_chars=2500, topic="四季")
    assert sum(b.target_chars for b in plan.beats) == 20000
    assert len(plan.beats) == 8


def test_prompt_excludes_creator_notes_by_default():
    bible = StoryBible(
        characters=[CharacterCardV2(name="阿远", description="渔人", creator_notes="SECRET")],
        boundaries=["不替用户作决定"],
    )
    plan = build_outline(target_visible_chars=5000, segment_chars=2500)
    msgs = build_segment_messages(
        bible=bible,
        plan=plan,
        beat=plan.beats[0],
        scene=__import__("app.services.narrative_schema", fromlist=["SceneState"]).SceneState(),
    )
    blob = msgs[0]["content"] + msgs[1]["content"]
    assert "SECRET" not in blob
    assert "不替用户作决定" in blob


def test_import_export_roundtrip():
    bible = extract_story_bible_from_text("角色：阿远\n世界规则：海边小镇\n禁止：不替用户行动")
    payload = export_config(bible)
    b2, scene = import_config(payload)
    assert b2.characters[0].name
    assert scene.version == 1


def test_agency_guard_flags_user_control_theft():
    report = check_segment("于是你决定了立刻离开。", min_chars=1)
    assert report.ok is False
    assert "user_agency_violation" in report.reasons


@pytest.mark.asyncio
async def test_orchestrator_reaches_target_on_single_assistant_message(tmp_settings):
    from app import db as dbmod

    dbmod._local.conn = dbmod._connect(tmp_settings.sqlite_path)
    provider = LongFakeProvider(chars_per_token=2.0)
    chat = ChatService(tmp_settings, provider, TokenEstimator(tmp_settings.model_path))
    orch = NarrativeOrchestrator(chat)
    events = []
    async for ev in orch.run(
        message="角色：阿远\n请写长篇四季农事说明文。",
        owner_id=None,
        target_visible_chars=5000,
        segment_chars=1200,
        segment_max_tokens=600,
        resource_check=False,
    ):
        events.append(ev)
    done = next(e for e in events if e["event"] == "done")
    body = done["data"]["message"]["content"]
    assert count_visible_chars(body) >= 5000
    assert done["data"]["job_id"]
    assert done["data"]["length_trace"]["visible_char_count"] >= 5000
    # Also prove the hard 20K path with the same orchestrator.
    events20 = []
    async for ev in orch.run(
        message="角色：阿清\n请写更长的正文。",
        owner_id=None,
        target_visible_chars=20000,
        segment_chars=2500,
        segment_max_tokens=1200,
        resource_check=False,
    ):
        events20.append(ev)
    done20 = next(e for e in events20 if e["event"] == "done")
    assert count_visible_chars(done20["data"]["message"]["content"]) >= 20000
    # Single assistant message in the conversation
    msgs = chat._load_history(done["data"]["conversation_id"])
    assistants = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistants) == 1
    # Segments persisted and rehashable
    from app.services import narrative_store as nstore

    segs = nstore.list_segments(done["data"]["job_id"])
    assert len(segs) >= 2
    assert nstore.reassemble_body(done["data"]["job_id"]) == body


def test_chat_routes_long_form_to_narrative(tmp_settings, monkeypatch):
    from app import db as dbmod
    from tests.conftest import local_http_client
    from app.services.narrative_resources import ResourceSnapshot

    monkeypatch.setattr(
        "app.services.narrative_resources.sample_resources",
        lambda: ResourceSnapshot(swap_free_mib=4096.0, swapout_pages=1, pages_free=500_000),
    )
    dbmod._local.conn = dbmod._connect(tmp_settings.sqlite_path)
    provider = LongFakeProvider(chars_per_token=2.0)
    chat = ChatService(tmp_settings, provider, TokenEstimator(tmp_settings.model_path))
    app = create_app(tmp_settings, chat=chat)
    with local_http_client(app) as client:
        r = client.post(
            "/chat",
            json={
                "message": "角色：阿远\n写长文",
                "stream": False,
                "profile": "long_form",
                "target_visible_chars": 3000,
                "segment_chars": 1000,
                "max_tokens": 500,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert count_visible_chars(body["message"]["content"]) >= 3000
        assert body.get("job_id")
        assert body["length_trace"]["visible_char_count"] >= 3000
