"""Typed scene state for immersive turns: fixtures F1–F7 (clothes, contact, space, beat, fold, isolation, cache)."""

from __future__ import annotations

import pytest

from app.providers.base import ChatChunk, ChatRequest

# One scene, two named people, one outer layer, one contact point, one imperative.
SCENE = {
    "setup": "地点：更衣室。林夏穿着风衣和连衣裙，里面是黑色内衣。",
    "undress": "沈川把林夏的风衣脱掉。",
    "contact": "沈川的手指按在林夏的腰上，慢慢往下。",
    "expect": {
        "place": "更衣室",
        "worn_after_undress": ["连衣裙", "内衣"],
        "removed": ["风衣"],
        "contact": "contact:沈川:腰",
    },
}
REDRESS = "林夏把风衣重新穿好，扣上了扣子。"
MOOD_ONLY = "更衣室的灯很暗，空气里有淡淡的香水味，镜子里映出两个人的影子。"
TELEPORT = "客厅的沙发上，林夏靠在沈川怀里。"
MOVED = "沈川把林夏抱进客厅，放在沙发上。"


def _graph(*turns: str):
    from app.services.scene_graph import SceneGraph

    graph = SceneGraph()
    for text in turns:
        graph.merge(text, role="user")
    return graph


def _kinds(missing: list[str], kind: str) -> list[str]:
    return [m for m in missing if m.startswith(kind + ":")]


def _scripted(bodies: list[str], calls: list[ChatRequest], finishes: list[str] | None = None):
    async def stream(request: ChatRequest):
        calls.append(request)
        i = min(len(calls), len(bodies)) - 1
        finish = (finishes or ["stop"] * len(bodies))[i]
        yield ChatChunk(id="c", model="fake", delta_content=bodies[i])
        yield ChatChunk(id="c", model="fake", finish_reason=finish, prompt_tokens=10, completion_tokens=20)
        yield ChatChunk(id="c", model="fake", wire_done=True)

    return stream


def _fence(request: ChatRequest) -> str:
    return next(
        (m.get("content") or "" for m in request.messages if m.get("id") == "context-fences"), ""
    )


def _scene_block(text: str) -> str:
    start = text.find("<scene_state>")
    end = text.find("</scene_state>")
    assert start >= 0 and end > start, text
    return text[start:end]


async def _chat(chat_service, message: str, **kwargs) -> list[dict]:
    opts = {"conversation_id": None, "stream": True, "profile": "immersive", "max_tokens": 256}
    opts.update(kwargs)
    return [ev async for ev in chat_service.chat(message=message, **opts)]


def _done(events: list[dict]) -> dict:
    dones = [e["data"] for e in events if e.get("event") == "done"]
    assert len(dones) == 1, [e.get("event") for e in events][-5:]
    return dones[0]


# F1 — clothes persistence


def test_f1_removed_outer_layer_is_typed_and_redress_is_reported():
    from app.services.fact_extractor import pins_absent_from_prose
    from app.services.scene_graph import slots_absent_from_prose

    graph = _graph(SCENE["setup"], SCENE["undress"])
    cast = graph.member("林夏")
    assert cast.clothes_layers == SCENE["expect"]["worn_after_undress"]
    assert cast.removed == SCENE["expect"]["removed"]
    assert "clothes:林夏:风衣:off" in graph.atoms()
    assert "clothes:林夏:内衣" in graph.atoms()

    missing = slots_absent_from_prose(graph, "沈川看着她。" + REDRESS)
    assert _kinds(missing, "clothes") == ["clothes:林夏:风衣:off"]
    assert _kinds(pins_absent_from_prose(graph.repair_atoms(), REDRESS), "clothes")
    assert not _kinds(slots_absent_from_prose(graph, "风衣落在长凳上，他没去捡。"), "clothes")


def test_f1_assistant_prose_cannot_redress_a_removed_layer():
    graph = _graph(SCENE["setup"], SCENE["undress"])
    graph.merge(REDRESS, role="assistant")
    assert graph.member("林夏").clothes_layers == SCENE["expect"]["worn_after_undress"]


async def test_f1_chat_repairs_redress_on_same_message(chat_service, fake_provider, monkeypatch):
    calls: list[ChatRequest] = []
    first = "沈川的手停在林夏的腰上。" + REDRESS
    fake_provider.stream = _scripted([first, "风衣还落在更衣室的长凳上。"], calls)  # type: ignore[method-assign]
    monkeypatch.setattr(
        chat_service.tokenizer, "continuation_completion_prompt", lambda m, **k: ("CONT", "")
    )

    events = await _chat(chat_service, SCENE["setup"] + SCENE["undress"], auto_continue=False)

    done = _done(events)
    assert len(calls) == 2
    assert done["pin_repair_count"] == 1
    content = done["message"]["content"]
    assert "重新穿好" not in content
    assert content.startswith("沈川的手停在林夏的腰上。")
    block = _scene_block(_fence(calls[0]))
    assert "已脱" in block and "风衣" in block and "内衣" in block
    assert "<repair>" not in _fence(calls[0])
    repair = _fence(calls[1])
    assert "<repair>" in repair and "风衣" in repair.split("<repair>", 1)[1]
    metas = [e["data"] for e in events if e.get("event") == "meta"]
    assert {m["message_id"] for m in metas} == {done["message"]["id"]}


# F2 — contact persistence


def test_f2_named_region_is_a_contact_slot_and_mood_only_prose_misses_it():
    from app.services.scene_graph import slots_absent_from_prose

    graph = _graph(SCENE["setup"], SCENE["contact"])
    assert SCENE["expect"]["contact"] in graph.atoms()
    assert graph.contact[-1].target == "林夏"
    assert _kinds(slots_absent_from_prose(graph, MOOD_ONLY), "contact") == [SCENE["expect"]["contact"]]
    assert not _kinds(slots_absent_from_prose(graph, "他的指腹压着她腰侧那一小块皮肤。"), "contact")


async def test_f2_chat_repair_hint_names_the_contact_region(chat_service, fake_provider, monkeypatch):
    calls: list[ChatRequest] = []
    fake_provider.stream = _scripted([MOOD_ONLY, "他的指腹压着她的腰。"], calls)  # type: ignore[method-assign]
    monkeypatch.setattr(
        chat_service.tokenizer, "continuation_completion_prompt", lambda m, **k: ("CONT", "")
    )

    done = _done(await _chat(chat_service, SCENE["setup"] + SCENE["contact"], auto_continue=False))

    assert done["pin_repair_count"] == 1
    assert done["message"]["content"].startswith(MOOD_ONLY)
    assert "腰" in _fence(calls[1]).split("<repair>", 1)[1]


# F3 — no teleport


def test_f3_place_holds_unless_prose_moves():
    from app.services.scene_graph import slots_absent_from_prose

    graph = _graph(SCENE["setup"])
    assert graph.space.place == SCENE["expect"]["place"]
    assert _kinds(slots_absent_from_prose(graph, TELEPORT), "space") == ["space:place:更衣室"]
    assert not _kinds(slots_absent_from_prose(graph, MOVED), "space")
    assert not _kinds(slots_absent_from_prose(graph, "更衣室的镜子蒙上一层雾。"), "space")

    drifted = graph.copy()
    drifted.merge(TELEPORT, role="assistant")
    assert drifted.space.place == "更衣室"
    moved = graph.copy()
    moved.merge(MOVED, role="assistant")
    assert moved.space.place == "客厅"


# F4 — beat advance on Continue


def test_f4_new_tokens_must_change_verb_contact_or_clothes():
    from app.services.scene_graph import beat_advanced

    graph = _graph(SCENE["setup"], SCENE["contact"])
    assert not beat_advanced(graph, "窗外的雨声很轻，灯光昏黄。")
    assert beat_advanced(graph, "沈川拉下林夏连衣裙的拉链，吻上她的锁骨。")


async def test_f4_continue_drops_closed_beat_and_counts_stub_hops(
    chat_service, fake_provider, monkeypatch
):
    closed = "沈川的手指揉着林夏的腰。"
    opening = "林夏靠在更衣镜前，呼吸有点乱。"
    prefixes: list[str] = []

    def fake_prompt(messages, **kwargs):
        prefixes.append(messages[-1]["content"])
        return (f"P{len(prefixes)}", "")

    monkeypatch.setattr(chat_service.tokenizer, "continuation_completion_prompt", fake_prompt)
    calls: list[ChatRequest] = []
    fake_provider.stream = _scripted(  # type: ignore[method-assign]
        [
            opening + closed,
            "窗外的雨声很轻，灯光昏黄。",
            "沈川拉下林夏连衣裙的拉链，吻上她的锁骨。",
            "林夏的内衣被推高，沈川含住她的胸口。",
            "沈川的唇沿着她锁骨往下，掌心仍按着腰窝慢慢加压。",
            "林夏的呼吸乱了一拍，手指扣进他的肩背。",
        ],
        calls,
    )

    done = _done(await _chat(chat_service, "继续", auto_continue=True, max_tokens=6144))

    assert len(calls) >= 4
    assert prefixes[0] == opening
    assert not prefixes[0].endswith(closed)
    assert done["stub_hops"] >= 1
    assert done["beat_hops"] >= 2


# F5 — fold keeps the graph


def _fold_history() -> list[dict]:
    filler = "镜面起了雾，两个人的影子叠在一起，谁都没有先开口。" * 12
    turns = [
        (SCENE["setup"], "沈川反手锁上更衣室的门。"),
        (SCENE["undress"], "风衣滑到长凳上，林夏的肩膀露了出来。"),
        ("再把林夏的连衣裙也脱掉。", "连衣裙堆在她脚边，只剩黑色内衣。"),
        (SCENE["contact"], "他的指腹压着她的腰，一路往下。"),
    ] + [(f"第{i}拍，继续。", filler) for i in range(6)]
    msgs: list[dict] = [{"id": "s", "role": "system", "content": "stable"}]
    for i, (user, assistant) in enumerate(turns):
        msgs.append({"id": f"u{i}", "role": "user", "content": user})
        msgs.append({"id": f"a{i}", "role": "assistant", "content": assistant})
    return msgs


def test_f5_folded_undress_survives_in_scene_state():
    from app.services.dialogue_context import build_dialogue_context
    from app.services.scene_graph import SceneGraph

    built = build_dialogue_context(
        _fold_history(),
        budget=700,
        estimate=len,
        recent_turn_target=4,
        min_recent_turns=4,
        fold_every_turns=4,
        graph=SceneGraph(),
    )

    assert built.folded_turns >= 4
    assert "u2" in built.dropped_ids
    lin = built.graph.member("林夏")
    assert lin.clothes_layers == ["内衣"]
    assert lin.removed == ["风衣", "连衣裙"]
    block = built.graph.fence()
    assert block.startswith("<scene_state>") and len(block) <= 800
    assert "内衣" in block and "连衣裙" in block
    ctx = next(m for m in built.messages if m.get("id") == "dialogue-context")
    assert "<scene_state>" not in ctx["content"]
    assert "clothing:" not in ctx["content"]


async def test_f5_chat_fence_keeps_inner_only_after_long_history(
    chat_service, fake_provider, monkeypatch
):
    cid = chat_service._create_conversation("", "m", "{}")
    for msg in _fold_history()[1:]:
        chat_service._insert_message(cid, msg["role"], msg["content"])
    calls: list[ChatRequest] = []
    fake_provider.stream = _scripted(["他的指腹压着她的腰，内衣的肩带滑落。"], calls)  # type: ignore[method-assign]

    await _chat(chat_service, "继续", conversation_id=cid, auto_continue=False)

    block = _scene_block(_fence(calls[0]))
    worn = next(line for line in block.splitlines() if line.startswith("cast 林夏"))
    assert "内衣" in worn and "已脱 风衣、连衣裙" in worn
    assert "穿着(外→内) 内衣 " in worn + " "


# F6 — isolation


@pytest.mark.parametrize("profile", ["interactive_dialogue", "balanced", "reasoning"])
async def test_f6_folded_non_immersive_request_has_no_scene_state_or_director_note(
    chat_service, fake_provider, monkeypatch, profile
):
    import app.services.chat as chat_mod

    real = chat_mod.resolve_profile
    monkeypatch.setattr(
        chat_mod, "resolve_profile", lambda name: {**real(name), "prompt_budget": 900}
    )
    cid = chat_service._create_conversation("", "m", "{}")
    for msg in _fold_history()[1:]:
        chat_service._insert_message(cid, msg["role"], msg["content"])
    calls: list[ChatRequest] = []
    fake_provider.stream = _scripted(["好。"], calls)  # type: ignore[method-assign]

    await _chat(chat_service, SCENE["contact"], conversation_id=cid, profile=profile, auto_continue=False)

    sent = "\n".join(m.get("content") or "" for m in calls[0].messages)
    assert "<history_summary>" in sent, "fixture must fold"
    for tag in ("<scene_state>", "<author_note>", "<repair>", "<must_keep>"):
        assert tag not in sent, (profile, tag)


# Live-sniff regressions (2-turn F1+F2 scene against the 9B)


def test_verb_before_possessive_is_not_a_cast_name():
    graph = _graph(SCENE["setup"])
    graph.merge("沈川手里拿着那件刚刚被她脱下的风衣。", role="assistant")
    assert [m.name for m in graph.cast] == ["林夏"]


def test_light_projected_on_mirror_is_not_sex_phase():
    graph = _graph(SCENE["setup"])
    graph.merge("光斜斜地切过穿衣镜，将林夏的身影投射在光滑的镜面之上。", role="assistant")
    assert graph.beat.phase == "approach"


def test_generic_room_is_not_a_teleport():
    from app.services.scene_graph import slots_absent_from_prose

    graph = _graph(SCENE["setup"])
    assert not _kinds(slots_absent_from_prose(graph, "房间里只剩下两个人的呼吸声。"), "space")


async def test_garment_nouns_are_not_object_pins_when_graph_owns_clothes(
    chat_service, fake_provider, monkeypatch
):
    calls: list[ChatRequest] = []
    fake_provider.stream = _scripted(  # type: ignore[method-assign]
        ["沈川脱下那件外套，搭在更衣室的衣架上。", "他的指腹压着她的腰。"], calls
    )
    first = await _chat(chat_service, SCENE["setup"], auto_continue=False)
    cid = next(e for e in first if e.get("event") == "meta")["data"]["conversation_id"]
    turn2 = len(calls)

    done = _done(await _chat(chat_service, SCENE["contact"], conversation_id=cid, auto_continue=False))

    fence = _fence(calls[turn2])
    assert _done(first)["pin_repair_count"] == 0
    assert "物件：外套" not in fence and "物件：裙" not in fence
    assert "专名：慢慢往下" not in fence
    inventory = [ln for ln in _scene_block(fence).splitlines() if ln.startswith("inventory:")]
    assert not any("外套" in ln or "裙" in ln for ln in inventory)
    assert done["pin_repair_count"] == 0


def test_undressing_agent_is_not_the_owner():
    graph = _graph("地点：更衣室。林夏穿着风衣和连衣裙，里面是黑色内衣。沈川把林夏的风衣脱掉。")
    graph.merge("她微微侧身，让沈川能够更方便地脱下这件外套。随着风衣的完全褪去，她轻轻吸了一口气。", role="assistant")
    shen = graph.member("沈川")
    assert shen is None or not shen.removed
    assert graph.focus == "林夏" and graph.actor == "沈川"


def test_touching_a_garment_part_is_not_body_contact():
    graph = _graph("地点：更衣室。林夏穿着风衣和连衣裙，里面是黑色内衣。沈川把林夏的风衣脱掉。")
    graph.merge("手里拿着那件刚刚被她脱下的风衣。指尖先触碰到风衣的肩部。", role="assistant")
    assert graph.actor == "沈川"
    assert graph.contact == []


def test_touched_body_owner_is_not_the_actor():
    graph = _graph(SCENE["setup"], SCENE["undress"], SCENE["contact"])
    graph.merge("他的手从她饱满的臀线一路滑向腿根。", role="assistant")
    assert graph.actor == "沈川"
    assert ("沈川", "林夏", "大腿") in [(c.who, c.target, c.body_region) for c in graph.contact]
    assert all(c.who != c.target for c in graph.contact)


def test_hem_slipping_off_the_thigh_is_not_undressing():
    graph = _graph(SCENE["setup"], SCENE["undress"])
    graph.merge("这一次，裙摆终于完全脱离了大腿的束缚。沈川撩起她的裙摆。", role="assistant")
    lin = graph.member("林夏")
    assert lin is not None
    assert lin.removed == ["风衣"] and lin.clothes_layers == ["连衣裙", "内衣"]
    assert lin.exposed == ["连衣裙敞开"]


def test_named_subject_removing_unworn_garment_owns_it():
    graph = _graph(SCENE["setup"])
    graph.merge("沈川脱下那件外套，搭在衣架上。他的指腹压着她的腰。", role="assistant")
    shen = graph.member("沈川")
    assert shen is not None and shen.removed == ["外套"]
    lin = graph.member("林夏")
    assert lin is not None and "外套" not in lin.removed
    assert [(c.who, c.target, c.body_region) for c in graph.contact] == [("沈川", "林夏", "腰")]


# F7 — cache dodge still holds after the next-beat strip


async def test_f7_next_beat_strip_marks_unshortened_prefix_used(
    chat_service, fake_provider, monkeypatch, require_chat_template
):
    import app.services.continuation as cont

    real = cont.shorten_until_unused
    seen: list[tuple[str, list[str], str]] = []

    def spy(native, *, encode, decode, used):
        prompt, tail = real(native, encode=encode, decode=decode, used=used)
        seen.append((native, list(used or []), prompt))
        return prompt, tail

    monkeypatch.setattr(cont, "shorten_until_unused", spy)
    opening = "林夏靠在更衣镜前，呼吸有点乱。"
    closed = "沈川的手指揉着林夏的腰。"
    fill = "".join(f"第{i}下，他吻过她的锁骨，又揉着她的腰。" for i in range(260))
    calls: list[ChatRequest] = []
    fake_provider.stream = _scripted([opening + closed, fill], calls)  # type: ignore[method-assign]

    done = _done(await _chat(chat_service, "继续", auto_continue=True, max_tokens=6144))

    assert len(calls) == 2 and seen
    native, used, prompt = seen[0]
    assert native.rstrip().endswith(opening)
    assert closed not in native
    assert native in used
    assert prompt != native and native.startswith(prompt)
    assert (calls[1].extra or {}).get("raw_prompt") == prompt
    assert done["message"]["content"].startswith(opening)
