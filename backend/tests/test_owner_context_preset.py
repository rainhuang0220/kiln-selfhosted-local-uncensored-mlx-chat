"""Owner failure: 技师×顾客 live line + ~2800字参考 must stay off-stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.providers.base import ChatChunk, ChatRequest
from app.services.scene_graph import SceneGraph
from app.services.scene_state_store import SceneStateStore
from app.services.style_bank import STYLE_FENCE_NOTE, split_style_corpus


FX = json.loads((Path(__file__).parent / "fixtures" / "style_corpus_massage.json").read_text("utf-8"))
_BASE = "".join(FX["paragraphs"]) + FX["techniques"] + FX["register"]
# Pad to ~2800 chars so the fixture matches the owner's live blob size.
_PAD = (
    "这些名字和场景只作幻想与性癖参考，不是当前风俗店里正在发生的事。"
    "顾客可以把它们当作背景资料，技师不应把它们念成眼前包间的情节。"
    "若未点名，参考人物一律不在场，也不进入当前扮演。"
    "店里只有技师和顾客两人；阳台、旧书店、影棚、健身房都不在这一拍。"
    "性癖与幻想可以存档，但当前对话必须留在风俗店的服务现场。"
)
CORPUS = _BASE + _PAD + ("参考资料补白。" * max(0, (2800 - len(_BASE + _PAD) + 6) // 7))
OFFSTAGE = [item["name"] for item in FX["offstage"]]
assert len(OFFSTAGE) == 10
assert len(CORPUS) >= 2800

# Exact live owner sentence — not the massage-shop fixture live line.
OWNER_LIVE = "你是一个风俗店的技师，我是你的顾客。"
OWNER_MARKER = "以下内容是我的信息背景和性癖参考，或者幻想参考。"
OWNER_MESSAGE = f"{OWNER_LIVE}\n{OWNER_MARKER}\n{CORPUS}"

MARKER_VARIANTS = [
    OWNER_MARKER,
    "以下内容是我的信息背景和性癖参考，或者幻想参考",
    "以下内容是（信息背景和性癖参考）",
    "以下内容是(幻想参考)",
    "信息背景",
    "性癖参考",
    "幻想参考",
    "以下内容是",
]


@pytest.mark.parametrize("marker", MARKER_VARIANTS)
def test_owner_markers_keep_shop_roles_live(marker):
    message = f"{OWNER_LIVE}\n{marker}\n{CORPUS}"
    split = split_style_corpus(message)
    assert "技师" in split.live and "顾客" in split.live
    assert "风俗店" in split.live
    assert all(name not in split.live for name in OFFSTAGE)
    assert len(split.corpus) >= 2400
    assert all(name in split.corpus for name in OFFSTAGE)


async def test_owner_shop_line_never_recaps_reference_blob(chat_service, fake_provider):
    calls: list[ChatRequest] = []

    async def stream(request: ChatRequest):
        calls.append(request)
        yield ChatChunk(id="test", model="fake", delta_content="技师站在顾客身旁，只谈这一间店。")
        yield ChatChunk(id="test", model="fake", finish_reason="stop", prompt_tokens=10, completion_tokens=20)
        yield ChatChunk(id="test", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]
    events = [
        event
        async for event in chat_service.chat(
            message=OWNER_MESSAGE,
            conversation_id=None,
            stream=True,
            profile="immersive",
            auto_continue=False,
            max_tokens=128,
        )
    ]
    assert not [event for event in events if event.get("event") == "error"]
    cid = next(event for event in events if event.get("event") == "meta")["data"]["conversation_id"]
    packed = "\n".join(item.get("content") or "" for item in calls[0].messages)
    assert "技师" in packed and "顾客" in packed
    assert CORPUS not in packed
    assert all(name not in packed for name in OFFSTAGE)
    assert "<style_bank>" in packed
    assert "不在当前场面" in packed or "此刻未发生" in packed or "勿复述" in packed
    assert "参考情节" in packed or "参考人物与事件" in packed or "勿复述" in STYLE_FENCE_NOTE or "勿复述" in packed
    graph = SceneGraph.from_dict(SceneStateStore().get(cid).graph)
    cast_names = {person.name for person in graph.cast}
    assert all(name not in cast_names for name in OFFSTAGE)


async def test_naming_one_offstage_retrieves_only_that_one(chat_service, fake_provider):
    from app.services.context_presets import preview_preset, save_preset

    draft = preview_preset(OWNER_MESSAGE)
    draft["active_character"]["name"] = draft["active_character"]["name"] or "技师"
    target = next(c for c in draft["characters"] if c["name"] == "顾遥")
    target["notes"] = "只在参考里出现的前任"
    saved = save_preset("风俗店", draft, OWNER_MESSAGE, owner_id="owner-a")
    first = [
        event
        async for event in chat_service.chat(
            message="从当前店里这一拍继续。",
            conversation_id=None,
            stream=True,
            profile="immersive",
            auto_continue=False,
            max_tokens=128,
            owner_id="owner-a",
            context_preset_id=saved["id"],
        )
    ]
    cid = next(event for event in first if event.get("event") == "meta")["data"]["conversation_id"]
    second = [
        event
        async for event in chat_service.chat(
            message="顾遥是谁？只说她的背景，不切换当前场景。",
            conversation_id=cid,
            stream=True,
            profile="immersive",
            auto_continue=False,
            max_tokens=128,
            owner_id="owner-a",
        )
    ]
    assert not [event for event in second if event.get("event") == "error"]
    sent = "\n".join(m.get("content") or "" for m in fake_provider.calls[-1].messages)
    assert "reference_context" in sent and "只在参考里出现的前任" in sent
    assert "顾遥" in sent
    others = [n for n in OFFSTAGE if n != "顾遥"]
    assert sum(1 for n in others if n in sent) == 0
    cast = {m.name for m in SceneGraph.from_dict(SceneStateStore().get(cid).graph).cast}
    assert "顾遥" not in cast


async def test_who_is_in_my_background_does_not_stage_cast(chat_service, fake_provider):
    from app.services.context_presets import preview_preset, save_preset

    draft = preview_preset(OWNER_MESSAGE)
    draft["active_character"]["name"] = draft["active_character"]["name"] or "技师"
    saved = save_preset("风俗店背景问", draft, OWNER_MESSAGE, owner_id="owner-a")
    first = [
        event
        async for event in chat_service.chat(
            message="先从店里开始。",
            conversation_id=None,
            stream=True,
            profile="immersive",
            auto_continue=False,
            max_tokens=128,
            owner_id="owner-a",
            context_preset_id=saved["id"],
        )
    ]
    cid = next(event for event in first if event.get("event") == "meta")["data"]["conversation_id"]
    ask = [
        event
        async for event in chat_service.chat(
            message="我的背景里有谁",
            conversation_id=cid,
            stream=True,
            profile="immersive",
            auto_continue=False,
            max_tokens=128,
            owner_id="owner-a",
        )
    ]
    assert not [event for event in ask if event.get("event") == "error"]
    cast = {m.name for m in SceneGraph.from_dict(SceneStateStore().get(cid).graph).cast}
    assert all(name not in cast for name in OFFSTAGE)


def test_preview_edit_event_who_save_get_keeps_names(chat_service):
    from app.services.context_presets import get_preset, preview_preset, save_preset

    draft = preview_preset(OWNER_MESSAGE)
    draft["active_character"]["name"] = draft["active_character"]["name"] or "技师"
    event = next(e for e in draft["references"]["events"] if e.get("who"))
    original_who = list(event["who"])
    # UI often posts who as a joined string; round-trip must restore a list.
    editable = dict(draft)
    editable["references"] = {
        **draft["references"],
        "events": [{**event, "who": "、".join(original_who)}],
    }
    saved = save_preset("who-roundtrip", editable, OWNER_MESSAGE, owner_id="owner-a")
    got = get_preset(saved["id"], owner_id="owner-a")
    assert got is not None
    who = got["payload"]["references"]["events"][0]["who"]
    assert who == original_who
    assert all(name in who for name in original_who)


async def test_bound_preset_survives_three_turns_with_zero_of_ten(chat_service, fake_provider):
    from app.services.context_presets import preview_preset, save_preset

    draft = preview_preset(OWNER_MESSAGE)
    draft["active_character"]["name"] = draft["active_character"]["name"] or "技师"
    draft["active_scene"] = OWNER_LIVE
    draft["user_persona"] = "我是你的顾客。"
    saved = save_preset("绑定三轮", draft, OWNER_MESSAGE, owner_id="owner-a")
    first = [
        event
        async for event in chat_service.chat(
            message="从当前店里这一拍开始。",
            conversation_id=None,
            stream=True,
            profile="immersive",
            auto_continue=False,
            max_tokens=128,
            owner_id="owner-a",
            context_preset_id=saved["id"],
        )
    ]
    assert not [event for event in first if event.get("event") == "error"]
    cid = next(event for event in first if event.get("event") == "meta")["data"]["conversation_id"]
    for turn in ("继续。", "再近一点。", "别停。"):
        events = [
            event
            async for event in chat_service.chat(
                message=turn,
                conversation_id=cid,
                stream=True,
                profile="immersive",
                auto_continue=False,
                max_tokens=128,
                owner_id="owner-a",
            )
        ]
        assert not [event for event in events if event.get("event") == "error"]
        bound = chat_service._conversation_settings(cid)
        assert bound.get("context_preset_id") == saved["id"]
        assert OWNER_LIVE in (bound.get("context_preset_snapshot") or {}).get("active_scene", "")
        packed = "\n".join(m.get("content") or "" for m in fake_provider.calls[-1].messages)
        leaked = [name for name in OFFSTAGE if name in packed]
        assert leaked == [], leaked
        assert CORPUS not in packed
