"""Context IR is the contract between long-document parsing and chat routing."""

from pathlib import Path

from app.services.context_presets import (
    chat_frame_from_simple,
    preview_preset,
    reference_context_for_mention,
    style_bank_for_preset,
)


SOURCE = (Path(__file__).parent / "fixtures" / "preset_ten_people.txt").read_text("utf-8")


def test_compiler_types_source_spans_and_keeps_preferences_out_of_events():
    draft = preview_preset(SOURCE)
    ir = draft["context_ir"]
    assert ir["version"] == 2
    assert ir["persona"]["role"] == "风俗店的技师"
    assert ir["user_avatar"]["identity"] == "我是你的顾客"
    assert len(ir["entities"]) == 11
    assert len(ir["events"]) >= 20
    assert all(event["description"] == SOURCE[event["source_span"]["start"]:event["source_span"]["end"]] for event in ir["events"])
    assert any(r["subject"] == "褚衡" and r["object"] == "顾遥" and r["predicate"] == "cousin_of" for r in ir["relations"])
    assert any(r["subject"] == "方晏" and r["object"] == "沈知意" and r["predicate"] == "colleague_of" for r in ir["relations"])
    assert not any(r["subject"] == "方晏" and r["object"] == "user" for r in ir["relations"])
    assert ir["preferences"] and all(p["do_not_literalize"] for p in ir["preferences"])
    kinds = {segment["type"] for segment in ir["segments"]}
    assert {"ROLE_DEFINITION", "USER_AVATAR", "USER_BACKGROUND", "USER_PREFERENCE", "ENTITY_DEFINITION", "WORLD_EVENT"} <= kinds
    for segment in ir["segments"]:
        span = segment["source_span"]
        assert SOURCE[span["start"]:span["end"]] == segment["text"]
    assert not any("慢节奏" in event["description"] for event in ir["events"])
    assert "橙花披肩" not in ir["current_scene"]


def test_document_type_gold_sample_separates_six_information_classes():
    source = (
        "你是一名茶馆店主，我是顾客。以下内容是我的信息背景和幻想参考。"
        "现实背景：我在杭州工作。明确偏好：喜欢慢节奏。"
        "阿青是我的姐姐。小学三年级时阿青送我一本书。"
    )
    segments = preview_preset(source)["context_ir"]["segments"]
    actual = [item["type"] for item in segments]
    assert actual == [
        "ROLE_DEFINITION", "USER_AVATAR", "DOCUMENT_META", "USER_BACKGROUND",
        "USER_PREFERENCE", "ENTITY_DEFINITION", "WORLD_EVENT",
    ]


def test_story_corpus_does_not_turn_common_words_into_entities():
    import json

    fixture = json.loads((Path(__file__).parent / "fixtures" / "style_corpus_massage.json").read_text("utf-8"))
    source = "你是一个风俗店的技师，我是你的顾客。以下内容是我的幻想参考。" + "".join(fixture["paragraphs"]) + fixture["techniques"] + fixture["register"]
    names = {item["name"] for item in preview_preset(source)["context_ir"]["entities"]}
    assert len(names) == 10
    assert {"两个人", "店走廊", "文件", "只会", "婚礼"}.isdisjoint(names)


def test_router_compiles_roleplay_recall_and_identity_differently():
    from app.services.context_compiler import route_context

    ir = preview_preset(SOURCE)["context_ir"]
    roleplay = route_context(ir, "开始聊天")
    assert roleplay.intent == "roleplay"
    assert "风俗店的技师" in roleplay.fence
    assert "我是你的顾客" in roleplay.fence
    assert "慢节奏" in roleplay.fence
    assert "橙花披肩" not in roleplay.fence
    assert "顾遥" not in roleplay.fence

    recall = route_context(ir, "顾遥那天把钥匙放在哪里？")
    assert recall.intent == "recall"
    assert "顾遥" in recall.fence
    assert "钥匙放在桌上" in recall.fence
    assert "参考事件" in recall.fence

    identity = route_context(ir, "你是什么身份？")
    assert identity.intent == "identity"
    assert "风俗店的技师" in identity.fence
    assert "顾遥" not in identity.fence


def test_late_reference_claim_cannot_replace_avatar_and_style_is_typed():
    draft = preview_preset(SOURCE)
    frame = chat_frame_from_simple(draft, source_text=SOURCE)
    assert frame["user_persona"] == "我是你的顾客"
    assert frame["context_ir"]["user_avatar"]["identity"] == "我是你的顾客"
    assert reference_context_for_mention(frame, "你是什么身份？") is None
    style = style_bank_for_preset(draft, source_text=SOURCE)
    assert not style.preferences
    assert all("橙花披肩" not in item for item in [*style.register, *style.techniques, *style.preferences])
    assert not style.events


def test_typed_segment_edit_survives_save_and_changes_runtime_route(chat_service):
    from app.services.context_presets import get_preset, save_preset

    source = (
        "你是茶馆店主，我是顾客。以下是参考。"
        "明确偏好：喜欢慢节奏。顾遥是我同事。顾遥把钥匙放在桌上。"
    )
    draft = preview_preset(source)
    target = next(s for s in draft["context_ir"]["segments"] if "喜欢慢节奏" in s["text"])
    target["type"] = "DOCUMENT_META"
    saved = save_preset("类型修订", draft, source, owner_id="owner-v2")
    loaded = get_preset(saved["id"], owner_id="owner-v2")
    assert loaded is not None
    assert any(s["id"] == target["id"] and s["type"] == "DOCUMENT_META" for s in loaded["payload"]["context_ir"]["segments"])
    from app.services.context_compiler import route_context

    routed = route_context(loaded["payload"]["context_ir"], "开始聊天")
    assert "喜欢慢节奏" not in routed.fence


def test_conflicting_late_avatar_is_recorded_but_never_promoted():
    ir = preview_preset(SOURCE)["context_ir"]
    assert any("我是她妹妹" in item["evidence"] for item in ir["conflicts"])
    assert ir["user_avatar"]["identity"] == "我是你的顾客"


def test_school_year_and_yesterday_are_local_time_cues():
    source = (
        "你是茶馆店主，我是顾客。以下内容是幻想参考。"
        "阿青是我的姐姐。小学三年级时阿青送我一本书。"
        "昨天阿青又把那本书放回桌上。"
    )
    ir = preview_preset(source)["context_ir"]
    assert {event["time"] for event in ir["events"]} >= {"小学三年级", "昨天"}


def test_first_meeting_question_uses_active_persons_event_without_copying_other_history():
    from app.services.context_compiler import route_context

    source = (
        "你是茶馆店主阿青，我是顾客。以下内容是幻想参考。"
        "阿青是我旧友。我和阿青第一次见面在旧书店。"
        "顾遥是我的同事。顾遥昨天在车站等我。"
    )
    ir = preview_preset(source)["context_ir"]
    routed = route_context(ir, "第一次见面在哪里？", active_names=["阿青"])
    assert routed.intent == "recall"
    assert "旧书店" in routed.fence
    assert "顾遥昨天" not in routed.fence


def test_model_segment_labels_require_exact_source_and_cannot_promote_reference():
    from app.services.context_compiler import merge_segment_labels, route_context

    source = "你是茶馆店主，我是顾客。以下是参考。温柔的语气让我更放松。顾遥是我的同事。顾遥把钥匙放在桌上。"
    draft = preview_preset(source)
    pending = next(item for item in draft["context_ir"]["segments"] if "温柔的语气" in item["text"])
    bad = next(item for item in draft["context_ir"]["segments"] if "顾遥是" in item["text"])
    result = merge_segment_labels(source, draft, {
        "labels": [
            {"id": pending["id"], "type": "USER_PREFERENCE", "evidence": pending["text"]},
            {"id": bad["id"], "type": "ROLE_DEFINITION", "evidence": bad["text"]},
            {"id": "seg-999", "type": "USER_PREFERENCE", "evidence": "不存在的偏好"},
        ],
    })
    segments = {item["id"]: item for item in result["context_ir"]["segments"]}
    assert segments[pending["id"]]["type"] == "USER_PREFERENCE"
    assert segments[bad["id"]]["type"] != "ROLE_DEFINITION"
    assert "温柔的语气" in route_context(result["context_ir"], "开始聊天").fence


async def test_chat_prompt_routes_history_only_after_named_recall(chat_service, fake_provider):
    from app.services.context_presets import save_preset

    draft = preview_preset(SOURCE)
    saved = save_preset("V2 路由", draft, SOURCE, owner_id="owner-v2")
    first = [event async for event in chat_service.chat(
        message="开始聊天", conversation_id=None, stream=True,
        profile="immersive", auto_continue=False, max_tokens=128,
        owner_id="owner-v2", context_preset_id=saved["id"],
    )]
    cid = next(event for event in first if event.get("event") == "meta")["data"]["conversation_id"]
    first_prompt = "\n".join(message.get("content") or "" for message in fake_provider.calls[-1].messages)
    assert "风俗店的技师" in first_prompt
    assert "慢节奏" in first_prompt
    assert "橙花披肩" not in first_prompt
    assert "顾遥那天把钥匙" not in first_prompt

    second = [event async for event in chat_service.chat(
        message="顾遥那天把钥匙放在哪里？", conversation_id=cid, stream=True,
        profile="immersive", auto_continue=False, max_tokens=128, owner_id="owner-v2",
    )]
    assert not [event for event in second if event.get("event") == "error"]
    second_prompt = "\n".join(message.get("content") or "" for message in fake_provider.calls[-1].messages)
    assert "参考事件" in second_prompt
    assert "顾遥那天把钥匙放在桌上" in second_prompt
    assert "橙花披肩" not in second_prompt


OWNER_DOCS = (Path(__file__).resolve().parents[2] / "docs" / "测试长文本.md").read_text("utf-8")


def test_owner_docs_long_text_separates_permission_classes():
    """Owner fixture: /docs/测试长文本.md — prefs, avatar, entities, events must not collapse."""
    draft = preview_preset(OWNER_DOCS)
    ir = draft["context_ir"]
    kinds = {segment["type"] for segment in ir["segments"]}
    assert {"ROLE_DEFINITION", "USER_AVATAR", "USER_PREFERENCE", "ENTITY_DEFINITION", "WORLD_EVENT"} <= kinds
    assert "风俗店技师" in (ir["persona"].get("role") or "")
    assert "小雨" in (ir["user_avatar"].get("identity") or "")
    assert "测试长文本" not in (ir.get("current_scene") or "")
    assert "风俗店" in (ir.get("current_scene") or "")
    assert ir["preferences"] and all(p["do_not_literalize"] for p in ir["preferences"])
    names = {item["name"] for item in ir["entities"]}
    assert {"吴玉蕊", "白若霜"}.issubset(names)
    assert "同时" not in names and "可能只" not in names
    # Default hop must not stuff reference events into the generation frame.
    frame = chat_frame_from_simple(draft, source_text=OWNER_DOCS)
    assert frame["references"]["events"] == []
    from app.services.context_compiler import route_context

    open_hop = route_context(ir, "开始聊天")
    assert open_hop.intent == "roleplay"
    assert "吴玉蕊" not in open_hop.fence
    assert "白若霜" not in open_hop.fence
    recall = route_context(ir, "白若霜那天发生了什么？")
    assert recall.intent == "recall"
    assert "白若霜" in recall.fence
    assert "周柯" not in recall.fence


def test_mixed_authority_fixture_keeps_head_customer_over_tail_sister():
    mixed = (
        "你是一个风俗店技师，我是你的顾客。\n"
        "以下内容是我的信息背景和性癖参考，或者幻想参考。\n"
        "（喜欢被照顾感，括号内容供后续服务学习，禁止照搬成正在发生的事。）\n"
        "现实背景：我住在岭南，白天上班。\n"
        "吴玉蕊，20岁，姐姐。\n"
        "升入小学三年级的时候白若霜带我去做检查。\n"
        "我叫小雨。\n"
        "顾遥那天把钥匙放在桌上。顾遥是我前公司的同事。\n"
        "我是她妹妹。\n"
    ) + SOURCE
    draft = preview_preset(mixed)
    ir = draft["context_ir"]
    assert "顾客" in (ir["user_avatar"].get("identity") or "")
    assert "妹妹" not in (ir["user_avatar"].get("identity") or "")
    assert any("我是她妹妹" in (c.get("evidence") or "") for c in ir["conflicts"])
    kinds = {segment["type"] for segment in ir["segments"]}
    assert {"ROLE_DEFINITION", "USER_AVATAR", "USER_PREFERENCE", "USER_BACKGROUND", "ENTITY_DEFINITION", "WORLD_EVENT"} <= kinds
    frame = chat_frame_from_simple(draft, source_text=mixed)
    assert frame["references"]["events"] == []
