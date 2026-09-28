"""Regression coverage for an adult, non-explicit dense narrative paste."""

from pathlib import Path


SOURCE = (Path(__file__).parent / "fixtures" / "preset_dense_adult_twelve.txt").read_text("utf-8")
PEOPLE = {
    "顾岚", "沈知夏", "唐书瑶", "陆清禾", "许明川", "林曼",
    "周以宁", "贺雨", "程星竹", "叶舒", "江遥", "苏檀",
}


def test_dense_adult_paste_keeps_every_named_person():
    from app.services.context_presets import preview_preset, public_studio_payload

    assert len(SOURCE) >= 1000
    draft = preview_preset(SOURCE)
    public = public_studio_payload(draft)
    names = {person["name"] for person in public["characters"]}
    assert PEOPLE <= names
    assert len(public["characters"]) <= 16
    assert all(name not in draft["current_scene"] for name in PEOPLE)
    assert "桌上" in draft["current_scene"] and "箱单" in draft["current_scene"]
    assert "上面这些人物" not in draft["current_scene"]
    assert len(draft["context_ir"]["entities"]) >= 12


def test_model_fill_cannot_invent_identity_or_event_for_known_name():
    import json

    from app.services.context_presets import merge_people_extract, preview_preset

    draft = preview_preset(SOURCE)
    result = merge_people_extract(
        SOURCE,
        draft,
        json.dumps({"characters": [{
            "name": "沈知夏",
            "identity": "秘密飞行员",
            "one_event": "驾驶飞机抵达火星",
        }]}),
    )
    person = next(p for p in result["characters"] if p["name"] == "沈知夏")
    assert "飞行员" not in person["identity"]
    assert "火星" not in (person.get("one_event") or "")


def test_model_fill_cannot_borrow_a_nearby_persons_role():
    import json

    from app.services.context_presets import merge_people_extract, preview_preset

    draft = preview_preset(SOURCE)
    result = merge_people_extract(
        SOURCE,
        draft,
        json.dumps({"characters": [{
            "name": "沈知夏",
            "identity": "负责工作室的账目",
        }]}),
    )
    person = next(p for p in result["characters"] if p["name"] == "沈知夏")
    assert person["identity"] != "负责工作室的账目"


async def test_direct_dense_paste_binds_compiled_context_for_followup(chat_service, fake_provider):
    events = [event async for event in chat_service.chat(
        message=SOURCE,
        conversation_id=None,
        stream=True,
        profile="immersive",
        auto_continue=False,
        max_tokens=128,
    )]
    assert not [event for event in events if event.get("event") == "error"]
    cid = next(event for event in events if event.get("event") == "meta")["data"]["conversation_id"]
    frame = chat_service._conversation_settings(cid).get("context_preset_snapshot")
    assert frame and frame["context_ir"]["version"] == 2
    assert len(frame["context_ir"]["entities"]) >= 12
    sent = "\n".join(m.get("content") or "" for m in fake_provider.calls[0].messages)
    assert "<active_context>" in sent
    assert "旧书修复工作室" in sent
    assert "沈知夏" not in sent
    assert "先从当前已知的物件或动作推进" in sent
    assert "最后一个身体动作" not in sent
    system = next(m["content"] for m in fake_provider.calls[0].messages if m["role"] == "system")
    assert "未给出的光线、气味、衣着" in system
    assert "没有写明的物件内容和检查结果不能先断言" in system
    assert "不要增加未写明的在场物件" in system
    assert "正常一拍至少 1500 字" not in system

    followup = [event async for event in chat_service.chat(
        message="沈知夏是谁？",
        conversation_id=cid,
        stream=True,
        profile="immersive",
        auto_continue=False,
        max_tokens=128,
    )]
    assert not [event for event in followup if event.get("event") == "error"]
    recall = "\n".join(m.get("content") or "" for m in fake_provider.calls[-1].messages)
    assert "<reference_context>" in recall
    assert "沈知夏" in recall


async def test_first_compiled_document_turn_does_not_force_long_auto_continuation(chat_service, fake_provider):
    events = [event async for event in chat_service.chat(
        message=SOURCE,
        conversation_id=None,
        stream=True,
        profile="immersive",
        max_tokens=128,
    )]
    assert not [event for event in events if event.get("event") == "error"]
    assert len(fake_provider.calls) == 1


async def test_attached_document_with_roleplay_request_uses_same_compiler(chat_service, fake_provider):
    wrapped = "请按这个设定开始当前场景。\n# File: adult_reference.txt\n" + SOURCE
    events = [event async for event in chat_service.chat(
        message=wrapped,
        conversation_id=None,
        stream=True,
        profile="immersive",
        auto_continue=False,
        max_tokens=128,
    )]
    assert not [event for event in events if event.get("event") == "error"]
    cid = next(event for event in events if event.get("event") == "meta")["data"]["conversation_id"]
    frame = chat_service._conversation_settings(cid).get("context_preset_snapshot")
    assert frame and len(frame["context_ir"]["entities"]) >= 12
