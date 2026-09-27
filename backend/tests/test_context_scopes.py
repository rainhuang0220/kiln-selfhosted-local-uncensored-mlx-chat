"""A long reference must not become the current scene or its remembered cast."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.providers.base import ChatChunk, ChatRequest
from app.services.scene_graph import SceneGraph
from app.services.scene_state_store import SceneStateStore
from app.services.style_bank import split_style_corpus


FX = json.loads((Path(__file__).parent / "fixtures" / "style_corpus_massage.json").read_text("utf-8"))
CORPUS = "".join(FX["paragraphs"]) + FX["techniques"] + FX["register"]
OFFSTAGE = [item["name"] for item in FX["offstage"]]
NATURAL_MARKER = "以下内容是我的信息背景和性癖参考，或者幻想参考。"
HEAD = f"{FX['live']}\n{NATURAL_MARKER}\n{CORPUS}"
TAIL = f"{NATURAL_MARKER}\n{CORPUS}\n请回到当前按摩店包间：{FX['live']}"


@pytest.mark.parametrize("message", [HEAD, TAIL], ids=["live-first", "live-last"])
def test_natural_reference_boundary_keeps_only_explicit_scene_live(message):
    split = split_style_corpus(message)
    assert "按摩店" in split.live
    assert len(split.corpus) >= 2400
    assert all(name in split.corpus and name not in split.live for name in OFFSTAGE)
    assert "阳台" not in split.live


@pytest.mark.parametrize("message", [HEAD, TAIL], ids=["live-first", "live-last"])
async def test_natural_reference_never_enters_prompt_or_scene(chat_service, fake_provider, message):
    calls: list[ChatRequest] = []

    async def stream(request: ChatRequest):
        calls.append(request)
        yield ChatChunk(id="test", model="fake", delta_content="阿沈留在包间，回应林夏。")
        yield ChatChunk(id="test", model="fake", finish_reason="stop", prompt_tokens=10, completion_tokens=20)
        yield ChatChunk(id="test", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]
    events = [
        event
        async for event in chat_service.chat(
            message=message,
            conversation_id=None,
            stream=True,
            profile="immersive",
            auto_continue=False,
            max_tokens=128,
        )
    ]
    assert not [event for event in events if event.get("event") == "error"]
    cid = next(event for event in events if event.get("event") == "meta")["data"]["conversation_id"]
    sent = "\n".join(item.get("content") or "" for item in calls[0].messages)
    graph = SceneGraph.from_dict(SceneStateStore().get(cid).graph)
    assert all(name not in sent for name in OFFSTAGE)
    assert all(name not in [person.name for person in graph.cast] for name in OFFSTAGE)
    assert graph.space.place != "阳台"
    stored = SceneStateStore().get(cid).style
    assert sum(name in {person["name"] for person in stored.get("names", [])} for name in OFFSTAGE) >= 8


def test_unmarked_current_scene_remains_live():
    message = "林夏在包间里把外套放好，阿沈问她今天想聊什么。"
    split = split_style_corpus(message)
    assert split.live == message
    assert split.corpus == ""


def test_offstage_stream_filter_hides_names_split_across_chunks():
    from app.services.style_bank import OffstageStreamFilter

    guard = OffstageStreamFilter({"顾遥", "苏棠"})
    output = guard.feed("她说顾") + guard.feed("遥来了，苏") + guard.feed("棠听见。") + guard.flush()
    assert "顾遥" not in output and "苏棠" not in output
    assert "她说" in output and "听见" in output


async def test_offstage_name_never_appears_in_streamed_delta(chat_service, fake_provider):
    async def stream(request: ChatRequest):
        for chunk in ("阿笙说顾", "遥不会来，", "茶还热着。"):
            yield ChatChunk(id="test", model="fake", delta_content=chunk)
        yield ChatChunk(id="test", model="fake", finish_reason="stop", prompt_tokens=10, completion_tokens=20)
        yield ChatChunk(id="test", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]
    message = "你是茶馆店主阿笙，我是客人林夏。\n以下内容是幻想参考。\n顾遥是我的前任。"
    events = [
        event async for event in chat_service.chat(
            message=message,
            conversation_id=None,
            stream=True,
            profile="immersive",
            auto_continue=False,
            max_tokens=128,
        )
    ]
    streamed = "".join(event["data"].get("content") or "" for event in events if event.get("event") == "delta")
    assert "顾遥" not in streamed
    assert "顾遥" not in next(event for event in events if event.get("event") == "done")["data"]["message"]["content"]


async def test_explicit_background_and_preference_survive_as_reference_profile(chat_service, fake_provider):
    message = (
        "你是茶馆店主阿笙，我是客人林夏。当前在茶馆。\n"
        "以下内容是我的背景和幻想参考。\n"
        "现实背景：我在上海工作。\n"
        "偏好：慢节奏、短句。\n"
        "幻想参考：顾遥在成都旧书店等我。"
    )
    events = [
        event
        async for event in chat_service.chat(
            message=message,
            conversation_id=None,
            stream=True,
            profile="immersive",
            auto_continue=False,
            max_tokens=128,
        )
    ]
    assert not [event for event in events if event.get("event") == "error"]
    cid = next(event for event in events if event.get("event") == "meta")["data"]["conversation_id"]
    sent = "\n".join(item.get("content") or "" for item in fake_provider.calls[0].messages)
    assert "我在上海工作" in sent and "慢节奏、短句" in sent
    assert "顾遥" not in sent and "成都" not in sent
    stored = SceneStateStore().get(cid).style
    assert stored["background_facts"] == ["我在上海工作"]
    assert stored["preferences"] == ["慢节奏、短句"]


def test_named_real_background_is_not_erased_by_offstage_scrub():
    from app.services.style_bank import StyleBank

    bank = StyleBank.from_corpus(
        "现实背景：我的前任叫顾遥，已经分手。\n"
        "偏好：在谈话中可以提起顾遥。\n"
        "幻想参考：顾遥在成都旧书店等待。"
    )
    assert "我的前任叫顾遥，已经分手" in bank.background_facts
    assert "在谈话中可以提起顾遥" in bank.preferences
    assert "顾遥" in bank.digest
    assert "成都" not in bank.digest


def test_asking_about_reference_person_does_not_stage_them():
    from app.services.style_bank import StyleBank

    bank = StyleBank.from_corpus("顾遥是她的旧友。顾遥在成都旧书店等过她。")
    assert "顾遥" in bank.offstage_scene(["顾遥是谁？"])
    assert "顾遥" in bank.offstage_scene(["我想聊聊顾遥的过去。"])
    assert "顾遥" not in bank.offstage_scene(["顾遥推开包间的门，走进来。"])
