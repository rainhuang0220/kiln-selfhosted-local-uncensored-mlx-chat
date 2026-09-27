"""Offstage 风格参考 corpora stay out of the on-stage SceneGraph (V07 StyleBank)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.providers.base import ChatChunk, ChatRequest
from app.services.fact_extractor import pins_absent_from_prose
from app.services.scene_graph import SceneGraph
from app.services.scene_state_store import SceneStateStore

FX = json.loads((Path(__file__).parent / "fixtures" / "style_corpus_massage.json").read_text("utf-8"))
OFFSTAGE = [o["name"] for o in FX["offstage"]]
LIVE_PAIR = set(FX["live_pair"])
CORPUS = "".join(FX["paragraphs"]) + FX["techniques"] + FX["register"]
HEAD = f'{FX["live"]}\n{FX["marker"]}（{CORPUS}）'
TAIL = f'{FX["marker"]}（{CORPUS}）\n{FX["live"]}'
SHOP_PROSE = "阿沈的掌心贴着林夏的腰，指腹打圈，慢慢往下推，林夏的呼吸乱了。"
TURN2 = "阿沈的指腹停在林夏的腰窝，林夏轻轻哼了一声。"
TURN3 = "苏棠推开包间的门，站在按摩床边看着林夏。"
AUTHOR_LINE = "括号/风格参考里的人名事件不要写进当前场面。"


def _leaks(text: str, allow: set[str] = frozenset()) -> list[str]:
    return [n for n in OFFSTAGE if n not in allow and n in (text or "")]


def _stream(calls: list[ChatRequest], body: str = SHOP_PROSE):
    async def stream(request: ChatRequest):
        calls.append(request)
        yield ChatChunk(id="c1", model="fake", delta_content=body)
        yield ChatChunk(
            id="c1", model="fake", finish_reason="stop", prompt_tokens=10, completion_tokens=20
        )
        yield ChatChunk(id="c1", model="fake", wire_done=True)

    return stream


async def _turn(chat_service, message: str, *, cid: str | None = None, profile: str = "immersive"):
    events = [
        ev
        async for ev in chat_service.chat(
            message=message,
            conversation_id=cid,
            stream=True,
            profile=profile,
            auto_continue=False,
            max_tokens=128,
        )
    ]
    assert not [e for e in events if e.get("event") == "error"], events[-2:]
    meta = next(e for e in events if e.get("event") == "meta")["data"]
    return meta["conversation_id"], events


def _sent(request: ChatRequest) -> str:
    return "\n".join(m.get("content") or "" for m in request.messages)


def _fence(request: ChatRequest) -> str:
    return next((m.get("content") or "" for m in request.messages if m.get("id") == "context-fences"), "")


def _cast(cid: str) -> list[str]:
    record = SceneStateStore().get(cid)
    return [m.name for m in SceneGraph.from_dict(record.graph if record else None).cast]


def test_fixture_has_owner_shape():
    for msg in (HEAD, TAIL):
        assert 2500 <= len(msg) <= 3500
    assert len(OFFSTAGE) == 10 and all(n in CORPUS for n in OFFSTAGE)
    assert not _leaks(FX["live"])


# ---- S1 / S7 split, head and tail ------------------------------------


@pytest.mark.parametrize("message", [HEAD, TAIL], ids=["head", "tail"])
def test_s1_s7_split_live_directive_from_style_corpus(message):
    from app.services.style_bank import split_style_corpus

    split = split_style_corpus(message)
    assert "按摩店技师" in split.live and "林夏" in split.live
    assert all(n in split.corpus for n in OFFSTAGE)
    assert not _leaks(split.live)
    assert FX["marker"] not in split.live
    assert split.live.strip() and split.corpus.strip()


def test_split_without_marker_is_all_live():
    from app.services.style_bank import split_style_corpus

    split = split_style_corpus(TURN2 + "（她轻轻哼了一声）")
    assert split.live == TURN2 + "（她轻轻哼了一声）" and split.corpus == ""


# ---- S3 bank --------------------------------------------------------


def test_s3_bank_names_digest_and_techniques():
    from app.services.style_bank import DIGEST_CAP, StyleBank, split_style_corpus

    bank = StyleBank.from_corpus(split_style_corpus(HEAD).corpus)
    names = [n.name for n in bank.names]
    assert sum(n in names for n in OFFSTAGE) >= 8, names
    assert not LIVE_PAIR & set(names)
    assert all(n.do_not_enter_scene for n in bank.names)
    assert bank.events or bank.techniques
    assert all(len(e.gist) <= 40 for e in bank.events)
    assert DIGEST_CAP <= 600 and 0 < len(bank.digest) <= DIGEST_CAP
    assert not _leaks(bank.digest)
    assert FX["planted_technique"] in bank.digest
    assert FX["planted_register"] in bank.digest
    fence = bank.fence()
    assert "不在当前场面" in fence and not _leaks(fence)
    assert len(fence) < len(CORPUS) // 3


# ---- S2 / S3 / S5 through the live chat path -------------------------


@pytest.mark.parametrize("message", [HEAD, TAIL], ids=["head", "tail"])
async def test_s2_s5_offstage_names_never_reach_scene_or_prompt(chat_service, fake_provider, message):
    calls: list[ChatRequest] = []
    fake_provider.stream = _stream(calls)  # type: ignore[method-assign]
    cid, _ = await _turn(chat_service, message)

    cast = _cast(cid)
    assert set(cast) == LIVE_PAIR, cast
    record = SceneStateStore().get(cid)
    graph = json.dumps(record.graph, ensure_ascii=False)
    assert not _leaks(graph), graph
    fence = _fence(calls[0])
    assert "<scene_state>" in fence
    assert not _leaks(fence), fence
    # The raw 2.5k corpus is not the prompt body; the live directive is.
    sent = _sent(calls[0])
    assert not _leaks(sent)
    assert FX["paragraphs"][0][:20] not in sent
    assert "按摩店技师" in sent
    # S5: labeled style fence, user side only.
    assert "<style_bank>" in fence and "不在当前场面" in fence
    assert AUTHOR_LINE in fence
    for m in calls[0].messages:
        if m.get("role") == "system":
            assert "<style_bank>" not in (m.get("content") or "")
            assert not _leaks(m.get("content") or "")
    # S3: bank stored next to graph_json, not inside it.
    assert "style_bank" not in record.graph and "names" not in record.graph
    stored = [n["name"] for n in record.style.get("names", [])]
    assert sum(n in stored for n in OFFSTAGE) >= 8, stored


async def test_s4_repair_never_demands_an_offstage_name(chat_service, fake_provider):
    calls: list[ChatRequest] = []
    fake_provider.stream = _stream(calls, body="她只是点了点头。")  # type: ignore[method-assign]
    cid, _ = await _turn(chat_service, HEAD)

    for request in calls:
        assert not _leaks(_sent(request))
    _, snapshot = chat_service._build_payload(
        chat_service._load_history(cid),
        max_tokens=128,
        enable_thinking=False,
        reasoning_effort="medium",
        conversation_id=cid,
        owner_id=None,
        profile_name="immersive",
        keep_pins=True,
    )
    pins = snapshot["keep_pins"]
    assert not [p for p in pins if _leaks(p)], pins
    missing = pins_absent_from_prose(pins, SHOP_PROSE)
    assert not [p for p in missing if _leaks(p)], missing


# ---- S6 interactive ---------------------------------------------------


async def test_s6_interactive_gets_no_style_bank_or_author_line(chat_service, fake_provider):
    calls: list[ChatRequest] = []
    fake_provider.stream = _stream(calls)  # type: ignore[method-assign]
    await _turn(chat_service, HEAD, profile="interactive_dialogue")

    sent = _sent(calls[0])
    assert "<style_bank>" not in sent and AUTHOR_LINE not in sent


# ---- S8 persist + retrieve one ---------------------------------------


async def test_s8_bank_persists_and_only_the_named_one_walks_on(chat_service, fake_provider):
    calls: list[ChatRequest] = []
    fake_provider.stream = _stream(calls)  # type: ignore[method-assign]
    cid, _ = await _turn(chat_service, HEAD)
    await _turn(chat_service, TURN2, cid=cid)

    record = SceneStateStore().get(cid)
    assert sum(n["name"] in OFFSTAGE for n in record.style.get("names", [])) >= 8
    assert not _leaks(" ".join(_cast(cid)))
    assert "<style_bank>" in _fence(calls[1])
    assert not _leaks(_sent(calls[1]))

    await _turn(chat_service, TURN3, cid=cid)
    assert not _leaks(" ".join(_cast(cid)), allow={"苏棠"})
    assert not _leaks(_sent(calls[2]), allow={"苏棠"})
    assert "苏棠" in _sent(calls[2])
