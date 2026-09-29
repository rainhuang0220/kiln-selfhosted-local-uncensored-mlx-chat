"""Reviewed presets bind a stable active role and keep reference people offstage."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.scene_graph import SceneGraph
from app.services.scene_state_store import SceneStateStore


FX = json.loads((Path(__file__).parent / "fixtures" / "style_corpus_massage.json").read_text("utf-8"))
CORPUS = "".join(FX["paragraphs"]) + FX["techniques"] + FX["register"]
SOURCE = FX["live"] + "\n以下内容是我的信息背景和幻想参考。\n" + CORPUS
OFFSTAGE = [item["name"] for item in FX["offstage"]]


def test_preview_extracts_editable_active_role_and_reference_people():
    from app.services.context_presets import preview_preset

    draft = preview_preset(SOURCE)
    assert "包间" in draft["current_scene"]
    assert all(name not in draft["current_scene"] for name in OFFSTAGE)
    names = {c["name"] for c in draft["characters"]}
    assert "阿沈" in names
    assert sum(1 for name in OFFSTAGE if name in names) >= 8
    assert "reference_people" not in draft
    assert "references" not in draft


def test_explicit_real_background_and_preference_are_separate_from_fantasy():
    from app.services.context_presets import preview_preset

    text = (
        "你是茶馆店主阿笙，我是顾客林夏。\n"
        "以下内容是背景和幻想参考。\n"
        "现实背景：我在上海工作。\n"
        "偏好：慢节奏、短句。\n"
        "幻想参考：顾遥在成都的旧书店等我。"
    )
    draft = preview_preset(text)
    assert "上海" in draft["me"]["real_background"]
    assert "慢节奏" in draft["me"]["explicit_prefs"] or "短句" in draft["me"]["explicit_prefs"]
    assert "顾遥" not in draft["current_scene"]
    assert "成都" not in draft["me"]["real_background"]


def test_preset_storage_is_owner_scoped_and_editable(chat_service):
    from app.services.context_presets import get_preset, list_presets, preview_preset, save_preset

    draft = preview_preset(SOURCE)
    saved = save_preset("包间场景", draft, SOURCE, owner_id="owner-a")
    assert saved["payload"]["current_scene"] == draft["current_scene"]
    assert get_preset(saved["id"], owner_id="owner-b") is None
    assert list_presets(owner_id="owner-b") == []
    draft["me"]["explicit_prefs"] = "短句"
    updated = save_preset("修订场景", draft, SOURCE, owner_id="owner-a", preset_id=saved["id"])
    assert updated["title"] == "修订场景"
    assert get_preset(saved["id"], owner_id="owner-a")["payload"]["me"]["explicit_prefs"] == "短句"


def test_incomplete_preset_must_not_be_saved(chat_service):
    import pytest
    from app.services.context_presets import save_preset

    with pytest.raises(ValueError, match="current scene"):
        save_preset("空设定", {"characters": [{"name": "阿青", "identity": "茶师"}]}, "", owner_id="owner-a")


def test_context_preset_routes_preview_save_edit_and_card_alias(client):
    preview = client.post("/context/presets/preview", json={"text": SOURCE})
    assert preview.status_code == 200
    draft = preview.json()["draft"]
    assert any(c["name"] == "阿沈" for c in draft["characters"])
    assert client.get("/context/cards").status_code == 200
    created = client.post("/context/presets", json={"title": "包间", "payload": draft, "source_text": SOURCE})
    assert created.status_code == 200, created.text
    saved = created.json()
    assert client.get("/context/presets").json()["data"][0]["id"] == saved["id"]
    assert client.get(f"/context/presets/{saved['id']}").json()["source_text"] == SOURCE
    edited = client.patch(f"/context/presets/{saved['id']}", json={"title": "修订包间"})
    assert edited.status_code == 200 and edited.json()["version"] == 2
    assert edited.json()["title"] == "修订包间"


async def test_selected_preset_freezes_active_frame_and_seeds_offstage_bank(chat_service, fake_provider):
    from app.services.context_presets import preview_preset, save_preset

    draft = preview_preset(SOURCE)
    draft["me"]["identity"] = "我是来店里的客人林夏。"
    draft["me"]["real_background"] = "我在上海工作"
    draft["me"]["explicit_prefs"] = "短句慢节奏"
    saved = save_preset("包间场景", draft, SOURCE, owner_id="owner-a")
    events = [
        event
        async for event in chat_service.chat(
            message="请从现在这一拍继续。",
            conversation_id=None,
            stream=True,
            profile="immersive",
            auto_continue=False,
            max_tokens=128,
            owner_id="owner-a",
            context_preset_id=saved["id"],
        )
    ]
    assert not [event for event in events if event.get("event") == "error"]
    cid = next(event for event in events if event.get("event") == "meta")["data"]["conversation_id"]
    sent = "\n".join(m.get("content") or "" for m in fake_provider.calls[0].messages)
    assert "包间" in sent and "我是来店里的客人林夏" in sent
    # V16: preference hint packs on default hop; confirmed_background is asked-only.
    assert "短句慢节奏" not in sent
    assert "confirmed_background" not in sent
    assert all(name not in sent for name in OFFSTAGE)
    assert SceneStateStore().get(cid).style.get("names")
    # Asked hop may surface 现实设定.
    bg_events = [
        event
        async for event in chat_service.chat(
            message="我的现实背景是什么？",
            conversation_id=cid,
            stream=True,
            profile="immersive",
            auto_continue=False,
            max_tokens=128,
            owner_id="owner-a",
        )
    ]
    assert not [event for event in bg_events if event.get("event") == "error"]
    bg_sent = "\n".join(m.get("content") or "" for m in fake_provider.calls[-1].messages)
    assert "我在上海工作" in bg_sent
    changed = dict(draft)
    changed["current_scene"] = "旧书店"
    save_preset("改变后", changed, SOURCE, owner_id="owner-a", preset_id=saved["id"])
    for turn in ("下一拍。", "继续当前会面。", "继续说下去。"):
        subsequent = [
            event async for event in chat_service.chat(
                message=turn,
                conversation_id=cid,
                stream=True,
                profile="immersive",
                auto_continue=False,
                max_tokens=128,
                owner_id="owner-a",
            )
        ]
        assert not [event for event in subsequent if event.get("event") == "error"]
        stored = chat_service._conversation_settings(cid)["context_preset_snapshot"]
        assert "包间" in stored["active_scene"] and "旧书店" not in stored["active_scene"]
        sent = "\n".join(m.get("content") or "" for m in fake_provider.calls[-1].messages)
        assert "我是来店里的客人林夏" in sent
        assert "旧书店" not in sent


async def test_active_cast_and_named_reference_are_retrieved_with_scope(chat_service, fake_provider):
    from app.services.context_presets import preview_preset, save_preset

    draft = preview_preset(SOURCE)
    draft["characters"].append({"name": "阿岚", "identity": "同事", "one_event": "站在柜台边"})
    # Bind 阿岚 + primary as active; plant 阿岚 in the live scene so L0 may name them.
    draft["current_scene"] = (draft.get("current_scene") or "") + "阿岚站在柜台边。"
    saved = save_preset("多人场景", draft, SOURCE, owner_id="owner-a")
    # Mark 阿岚 active via ids from saved payload
    payload = saved["payload"]
    al_id = next(c["id"] for c in payload["characters"] if c["name"] == "阿岚")
    primary_id = payload["characters"][0]["id"]
    payload["active_character_ids"] = [primary_id, al_id]
    payload["current_scene"] = (payload.get("current_scene") or "") + ("阿岚站在柜台边。" if "阿岚" not in (payload.get("current_scene") or "") else "")
    for c in payload["characters"]:
        if c["name"] == "顾遥":
            c["identity"] = "旧友"
            c["one_event"] = "只在往事中认识林夏"
    saved = save_preset("多人场景", payload, SOURCE, owner_id="owner-a", preset_id=saved["id"])
    first = [event async for event in chat_service.chat(
        message="从当前场景开始。", conversation_id=None, stream=True,
        profile="immersive", auto_continue=False, max_tokens=128,
        owner_id="owner-a", context_preset_id=saved["id"],
    )]
    cid = next(event for event in first if event.get("event") == "meta")["data"]["conversation_id"]
    first_sent = "\n".join(m.get("content") or "" for m in fake_provider.calls[-1].messages)
    assert "阿岚" in first_sent
    assert "顾遥" not in first_sent
    assert "阿岚" in {m.name for m in SceneGraph.from_dict(SceneStateStore().get(cid).graph).cast}

    second = [event async for event in chat_service.chat(
        message="顾遥是谁？只说她的背景，不切换当前场景。", conversation_id=cid,
        stream=True, profile="immersive", auto_continue=False, max_tokens=128,
        owner_id="owner-a",
    )]
    assert not [event for event in second if event.get("event") == "error"]
    sent = "\n".join(m.get("content") or "" for m in fake_provider.calls[-1].messages)
    assert "参考人物：顾遥" in sent
    assert "顾遥" not in {m.name for m in SceneGraph.from_dict(SceneStateStore().get(cid).graph).cast}


def test_chat_lore_scope_excludes_other_cards(chat_service):
    from app.services.lorebook import list_entries, save_entry

    save_entry(keys=["花店"], content="全局资料", owner_id="owner-a")
    save_entry(keys=["花店"], content="角色甲资料", owner_id="owner-a", character_card_id="card-a")
    save_entry(keys=["花店"], content="角色乙资料", owner_id="owner-a", character_card_id="card-b")
    no_card = {item["content"] for item in list_entries(owner_id="owner-a", active_only=True)}
    card_a = {item["content"] for item in list_entries(owner_id="owner-a", character_card_id="card-a", active_only=True)}
    assert no_card == {"全局资料"}
    assert card_a == {"全局资料", "角色甲资料"}


def test_deep_analysis_requires_source_evidence_and_cannot_promote_fantasy():
    from app.services.context_presets import merge_deep_analysis, preview_preset

    draft = preview_preset(SOURCE)
    model_json = json.dumps({
        "active_character": {"personality": "温和", "evidence": "不存在的句子"},
        "reference_people": [
            {"name": "顾遥", "notes": "说话很急", "evidence": "顾遥吻她的时候很急"},
            {"name": "陌生人", "notes": "凭空捏造", "evidence": "没有的内容"},
        ],
        "possible_preferences": [{"quote": "不存在的偏好"}],
    }, ensure_ascii=False)
    merged = merge_deep_analysis(SOURCE, draft, model_json)
    assert merged["current_scene"] == draft["current_scene"]
    assert next(c for c in merged["characters"] if c["name"] == "顾遥").get("one_event") == "说话很急"
    assert all(c["name"] != "陌生人" for c in merged["characters"])
