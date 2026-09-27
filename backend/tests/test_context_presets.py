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
    assert "包间" in draft["active_scene"]
    assert all(name not in draft["active_scene"] for name in OFFSTAGE)
    assert draft["active_character"]["name"] == "阿沈"
    assert draft["active_character"]["scenario"] == draft["active_scene"]
    assert sum(name in {p["name"] for p in draft["references"]["people"]} for name in OFFSTAGE) >= 8
    assert all(p["scope"] == "reference" for p in draft["characters"] if p["name"] in OFFSTAGE)
    assert not any(name in " ".join(draft["references"]["register"]) for name in OFFSTAGE)


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
    assert draft["background_facts"] == ["我在上海工作"]
    assert draft["preferences"] == ["慢节奏、短句"]
    assert "顾遥" not in draft["active_scene"]
    assert "成都" not in draft["background_facts"]


def test_preset_storage_is_owner_scoped_and_editable(chat_service):
    from app.services.context_presets import get_preset, list_presets, preview_preset, save_preset

    draft = preview_preset(SOURCE)
    saved = save_preset("包间场景", draft, SOURCE, owner_id="owner-a")
    assert saved["payload"]["active_scene"] == draft["active_scene"]
    assert get_preset(saved["id"], owner_id="owner-b") is None
    assert list_presets(owner_id="owner-b") == []
    draft["active_character"]["speech_style"] = "短句"
    updated = save_preset("修订场景", draft, SOURCE, owner_id="owner-a", preset_id=saved["id"])
    assert updated["title"] == "修订场景"
    assert get_preset(saved["id"], owner_id="owner-a")["payload"]["active_character"]["speech_style"] == "短句"


def test_reference_event_participants_survive_ui_round_trip(chat_service):
    from app.services.context_presets import normalize_payload, preview_preset, style_bank_for_preset

    draft = preview_preset(SOURCE)
    event = next(event for event in draft["references"]["events"] if event["who"])
    editable = dict(draft)
    editable["references"] = {**draft["references"], "events": [
        {**event, "who": "、".join(event["who"])}
    ]}
    saved = normalize_payload(editable)
    assert saved["references"]["events"][0]["who"] == event["who"]
    assert style_bank_for_preset(saved).events[0].who == event["who"]


def test_editing_current_scene_updates_the_character_card_scenario():
    from app.services.context_presets import normalize_payload, preview_preset

    draft = preview_preset(SOURCE)
    draft["active_scene"] = "当前在茶室里交谈。"
    assert normalize_payload(draft)["active_character"]["scenario"] == "当前在茶室里交谈。"


def test_character_rows_are_authoritative_for_reference_people():
    from app.services.context_presets import normalize_payload, preview_preset, style_bank_for_preset

    draft = preview_preset(SOURCE)
    person = next(c for c in draft["characters"] if c["scope"] == "reference")
    old_name = person["name"]
    person["name"] = "新名字"
    person["role"] = "旧友"
    person["notes"] = "曾在外地一起工作"
    saved = normalize_payload(draft)
    assert {p["name"] for p in saved["references"]["people"]} == {
        c["name"] for c in saved["characters"] if c["scope"] == "reference"
    }
    assert old_name not in {p["name"] for p in saved["references"]["people"]}
    assert any(n.name == "新名字" and n.role_hint == "旧友" for n in style_bank_for_preset(saved).names)


def test_incomplete_preset_must_not_be_saved(chat_service):
    import pytest
    from app.services.context_presets import save_preset

    with pytest.raises(ValueError, match="current scene"):
        save_preset("空设定", {"active_character": {"name": "阿青"}}, "", owner_id="owner-a")
    with pytest.raises(ValueError, match="active character"):
        save_preset("空人物", {"active_scene": "茶室"}, "", owner_id="owner-a")


def test_context_preset_routes_preview_save_edit_and_card_alias(client):
    preview = client.post("/context/presets/preview", json={"text": SOURCE})
    assert preview.status_code == 200
    draft = preview.json()["draft"]
    assert draft["active_character"]["name"] == "阿沈"
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
    draft["user_persona"] = "我是来店里的客人林夏。"
    draft["background_facts"] = ["我在上海工作"]
    draft["preferences"] = ["短句慢节奏"]
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
    assert "我在上海工作" in sent and "短句慢节奏" in sent
    assert all(name not in sent for name in OFFSTAGE)
    assert SceneStateStore().get(cid).style.get("names")
    changed = dict(draft)
    changed["active_scene"] = "旧书店"
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
        assert "我是来店里的客人林夏" in sent and "我在上海工作" in sent
        assert "旧书店" not in sent


async def test_active_cast_and_named_reference_are_retrieved_with_scope(chat_service, fake_provider):
    from app.services.context_presets import preview_preset, save_preset

    draft = preview_preset(SOURCE)
    draft["characters"].append({"name": "阿岚", "role": "同事", "scope": "active", "notes": "站在柜台边"})
    target = next(c for c in draft["characters"] if c["name"] == "顾遥")
    target["role"] = "旧友"
    target["notes"] = "只在往事中认识林夏"
    saved = save_preset("多人场景", draft, SOURCE, owner_id="owner-a")
    first = [event async for event in chat_service.chat(
        message="从当前场景开始。", conversation_id=None, stream=True,
        profile="immersive", auto_continue=False, max_tokens=128,
        owner_id="owner-a", context_preset_id=saved["id"],
    )]
    cid = next(event for event in first if event.get("event") == "meta")["data"]["conversation_id"]
    first_sent = "\n".join(m.get("content") or "" for m in fake_provider.calls[-1].messages)
    assert "阿岚" in first_sent and "同事" in first_sent and "站在柜台边" in first_sent
    assert "顾遥" not in first_sent
    assert "阿岚" in {m.name for m in SceneGraph.from_dict(SceneStateStore().get(cid).graph).cast}

    second = [event async for event in chat_service.chat(
        message="顾遥是谁？只说她的背景，不切换当前场景。", conversation_id=cid,
        stream=True, profile="immersive", auto_continue=False, max_tokens=128,
        owner_id="owner-a",
    )]
    assert not [event for event in second if event.get("event") == "error"]
    sent = "\n".join(m.get("content") or "" for m in fake_provider.calls[-1].messages)
    assert "reference_context" in sent and "只在往事中认识林夏" in sent
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
    assert merged["active_scene"] == draft["active_scene"]
    assert merged["active_character"]["personality"] == ""
    assert "说话很急" in next(c["notes"] for c in merged["characters"] if c["name"] == "顾遥")
    assert all(c["name"] != "陌生人" for c in merged["characters"])
    assert "不存在的偏好" not in merged["preferences"]
