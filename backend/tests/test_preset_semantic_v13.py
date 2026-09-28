"""V13: a long paste yields source-grounded people and ordered events."""

from __future__ import annotations

import json
from pathlib import Path


SOURCE = (Path(__file__).parent / "fixtures" / "preset_ten_people.txt").read_text("utf-8")
PEOPLE = {"祁律", "顾遥", "褚衡", "林夏", "阿沈", "沈知意", "方晏", "叶澄", "裴晚", "阮疏", "岑照"}


def test_fast_pipeline_keeps_scene_separate_and_makes_evidence_timeline():
    from app.services.context_presets import preview_preset

    draft = preview_preset(SOURCE)
    assert {c["name"] for c in draft["characters"]} >= PEOPLE
    assert [c["name"] for c in draft["characters"][:3]] == ["祁律", "顾遥", "褚衡"]
    assert "橙花披肩" not in draft["current_scene"]
    timeline = draft["timeline"]
    assert 20 <= len(timeline) <= 40
    assert {name for event in timeline for name in event["who"]} >= PEOPLE
    assert [event["source_span"]["start"] for event in timeline] == sorted(
        event["source_span"]["start"] for event in timeline
    )
    for event in timeline:
        span = event["source_span"]
        assert SOURCE[span["start"]:span["end"]] == event["evidence"]
        assert event["scope"] == "reference"
        assert event["summary"]
        assert len(event["summary"]) <= 100
    assert not any(name in {"湿透", "方先", "钥匙放"} for event in timeline for name in event["who"])


def test_timeline_records_local_temporal_cues_without_inventing_global_dates():
    from app.services.context_presets import preview_preset

    timeline = preview_preset(SOURCE)["timeline"]
    qi = [event for event in timeline if "祁律" in event["who"]]
    assert qi[0]["order"] < qi[-1]["order"]
    assert any("那天" in event["when"] for event in qi)
    assert any("有一年夏天" in event["when"] for event in qi)
    assert any("毕业以后" in event["when"] for event in timeline if "阮疏" in event["who"])
    assert all(event["chronology"] == "source_order" for event in timeline)


def test_unformatted_long_paste_still_separates_people_and_events():
    from app.services.context_presets import preview_preset

    flat = SOURCE.replace("\n\n", "").replace("\n", "")
    draft = preview_preset(flat)
    assert {c["name"] for c in draft["characters"]} >= PEOPLE
    assert len(draft["timeline"]) >= 20
    assert {name for event in draft["timeline"] for name in event["who"]} >= PEOPLE
    assert all(name not in draft["current_scene"] for name in PEOPLE)
    assert all("不能盖过" not in event["summary"] for event in draft["timeline"])


def test_semantic_merge_can_link_implicit_event_only_with_valid_evidence():
    from app.services.context_presets import merge_people_extract, preview_preset

    source = (
        "你是茶馆店主，我是顾客。\n以下内容是幻想参考。\n"
        "顾遥是我以前的同事。顾遥问我要不要一起下楼。"
        "她后来把旧钥匙放在桌上。顾遥看了看窗外。"
    )
    draft = preview_preset(source)
    candidate = next(event for event in draft["timeline"] if event["needs_review"])
    name = candidate["suggested_who"][0]
    result = merge_people_extract(source, draft, json.dumps({
        "characters": [],
        "event_links": [
            {"id": candidate["id"], "who": [name], "evidence": candidate["evidence"]},
            {"id": "invented", "who": ["陌生人"], "evidence": "没有的句子"},
        ],
    }, ensure_ascii=False))
    linked = next(event for event in result["timeline"] if event["id"] == candidate["id"])
    assert linked["who"] == [name]
    assert linked["needs_review"] is False
    assert all("陌生人" not in event["who"] for event in result["timeline"])


def test_complete_people_array_survives_truncated_optional_links():
    from app.services.context_presets import merge_people_extract, preview_preset

    draft = preview_preset(SOURCE)
    for row in draft["characters"]:
        if row["name"] == "顾遥":
            row["identity"] = "待补"
    unfinished = '{"characters":[{"name":"顾遥","identity":"前公司的同事","one_event":""}],"event_links":['
    merged = merge_people_extract(SOURCE, draft, unfinished)
    assert next(row["identity"] for row in merged["characters"] if row["name"] == "顾遥") == "前公司的同事"


def test_model_cannot_add_a_person_without_exact_reference_evidence():
    from app.services.context_presets import merge_people_extract, preview_preset

    draft = preview_preset(SOURCE)
    invented = json.dumps({"characters": [
        {"name": "方先", "identity": "天气", "one_event": "下雨"},
        {"name": "陌生人", "identity": "朋友", "one_event": ""},
    ]}, ensure_ascii=False)
    result = merge_people_extract(SOURCE, draft, invented)
    assert {row["name"] for row in result["characters"]} == {row["name"] for row in draft["characters"]}


def test_timeline_survives_save_and_named_reference_recall(chat_service):
    from app.services.context_presets import get_preset, preview_preset, reference_context_for_mention, save_preset
    from app.services.character_cards import list_cards

    draft = preview_preset(SOURCE)
    saved = save_preset("十人回忆", draft, SOURCE, owner_id="owner-a")
    loaded = get_preset(saved["id"], owner_id="owner-a")
    assert loaded is not None
    assert all(card["scenario"] == "" for card in list_cards(owner_id="owner-a"))
    assert len(loaded["payload"]["timeline"]) == len(draft["timeline"])
    recalled = reference_context_for_mention(loaded["payload"], "顾遥那天发生了什么？")
    assert recalled and "顾遥" in recalled and "参考事件" in recalled
    assert "橙花披肩" not in recalled


def test_preview_http_round_trip_keeps_timeline(client):
    preview = client.post("/context/presets/preview", json={"text": SOURCE, "deep": False})
    assert preview.status_code == 200
    draft = preview.json()["draft"]
    assert len(draft["timeline"]) >= 20
    created = client.post(
        "/context/presets",
        json={"title": "十人回忆", "payload": draft, "source_text": SOURCE},
    )
    assert created.status_code == 200, created.text
    loaded = client.get("/context/presets/" + created.json()["id"])
    assert loaded.status_code == 200
    assert loaded.json()["payload"]["timeline"] == created.json()["payload"]["timeline"]
