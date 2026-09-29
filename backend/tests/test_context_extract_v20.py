"""V20: school-year words in a long paste are timeline cues, not a preview block."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "test"
WOVEN = (DOCS / "多人物交织场景_输入.md").read_text("utf-8")
GOLD = json.loads((DOCS / "多人物交织场景_标准结构.json").read_text("utf-8"))
NARRATOR = GOLD["narrator"]
GOLD_PEOPLE = [p["name"] for p in GOLD["people"] if p["name"] != NARRATOR]
RETRY_COPY = "模型没有分析，请重试。没有使用规则名册。"
MINOR_COPY = "内容涉及未满十八岁的人物"

GAOYI = (
    "高一那年唐宁把我叫到发球线。她让我把球抛高一点，说手腕别急着翻。"
    "如今我二十九岁，唐宁三十一岁，我们在成年人的业余排球馆又碰见了。"
    + "那天馆里人不多，她站在网前数我发了几个球，数到第十个就笑着让我换边。"
    "我记得地板上有一道旧划痕，她每次都踩在那道划痕后面起跳。" * 14
)
XIAOXUE = (
    "升入小学三年级的时候，陆遥已经在上初中。她每天放学都先去书店，再慢慢走回家。"
    "现在我坐在接待室里，对你说：我是你的顾客，你是技师许澄。"
    + "陆遥如今三十四岁，还留着那本薄册子，每答应别人一件事就把日期写在右上角。"
    "我看着接待室墙上的钟，想起她翻到那一页请人自己看的样子。" * 14
)


def _stub(payload: dict):
    calls: list = []

    async def complete(request):
        calls.append(request)
        return SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))

    complete.calls = calls
    return complete


def _public(draft):
    from app.services.context_presets import public_studio_payload

    return public_studio_payload(draft)


async def _extract(source: str, complete):
    from app.services.context_presets import extract_preview_preset

    return await extract_preview_preset(source, None, complete=complete)


def _no_minor_copy(draft) -> None:
    assert draft["extract"]["mode"] != "blocked"
    assert "未满十八" not in json.dumps(draft["extract"], ensure_ascii=False)
    assert "未满十八" not in json.dumps(_public(draft), ensure_ascii=False)


def test_school_year_openings_are_long_pastes_that_used_to_trip_the_gate():
    from app.services.context_compiler.binder import _UNDER18
    from app.services.context_presets import ALIAS_RESOLVE_MIN_CHARS

    for source in (GAOYI, XIAOXUE):
        assert len(source) >= max(900, ALIAS_RESOLVE_MIN_CHARS)
        assert _UNDER18.search(source[:240])


# U1 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_u1_gaoyi_opening_runs_stage_a():
    stub = _stub({"people": [
        {"name": "唐宁", "aliases": [], "identity": "排球馆里的成年队友", "one_event": ""},
    ]})
    draft = await _extract(GAOYI, stub)
    assert stub.calls
    assert draft["extract"]["model_ran"] is True
    assert draft["extract"]["mode"] == "model"
    assert "唐宁" in {row["name"] for row in _public(draft)["characters"]}
    _no_minor_copy(draft)


@pytest.mark.asyncio
async def test_u1_model_ran_follows_the_stub_not_the_school_year():
    async def prose(request):
        return SimpleNamespace(content="好的，我来分析一下。")

    draft = await _extract(GAOYI, prose)
    assert draft["extract"]["model_ran"] is False
    assert draft["extract"]["mode"] == "model_failed"
    _no_minor_copy(draft)


# U2 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_u2_xiaoxue_opening_with_present_day_parlor_is_not_blocked():
    stub = _stub({"people": [
        {"name": "陆遥", "aliases": [], "identity": "留着薄册子的成年人", "one_event": ""},
        {"name": "许澄", "aliases": [], "identity": "技师", "one_event": "", "present": True},
    ]})
    draft = await _extract(XIAOXUE, stub)
    assert stub.calls
    assert draft["extract"]["model_ran"] is True
    assert "接待室" in str(stub.calls[0].messages)
    assert {"陆遥", "许澄"} <= {row["name"] for row in _public(draft)["characters"]}
    _no_minor_copy(draft)


@pytest.mark.asyncio
async def test_u2_alias_resolver_still_asks_the_9b_on_a_school_year_opening():
    from app.services.context_presets import preview_preset, resolve_preview_aliases

    stub = _stub({"people": [], "aliases": {}})
    await resolve_preview_aliases(XIAOXUE, preview_preset(XIAOXUE), None, complete=stub)
    assert len(stub.calls) == 1


# U3 ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("source", [WOVEN, XIAOXUE])
async def test_u3_no_runner_is_empty_cards_and_the_retry_copy(source):
    from app.services.context_presets import extract_preview_preset

    draft = await extract_preview_preset(source, None)
    public = _public(draft)
    assert draft["extract"]["model_ran"] is False
    assert draft["extract"]["mode"] == "model_failed"
    assert public["characters"] == [] and public["timeline"] == []
    _no_minor_copy(draft)
    web = ROOT / "web" / "src"
    assert RETRY_COPY in (web / "api" / "context-presets.ts").read_text("utf-8")


def test_u3_endpoint_school_year_paste_without_json_is_retry_not_policy(client):
    response = client.post("/context/presets/preview", json={"text": XIAOXUE, "deep": True})
    assert response.status_code == 200
    draft = response.json()["draft"]
    assert draft["characters"] == []
    assert draft["extract"]["model_ran"] is False
    assert draft["extract"]["mode"] == "model_failed"
    assert "未满十八" not in response.text


# U4 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_u4_woven_fixture_still_extracts_the_gold_eleven():
    people = [
        {
            "name": p["name"],
            "aliases": ["姐姐"] if p["name"] == "陆遥" else [],
            "identity": p["identity"],
            "one_event": "",
            "present": p["name"] in {"许澄", NARRATOR},
        }
        for p in GOLD["people"]
    ]
    draft = await _extract(WOVEN, _stub({"people": people}))
    public = _public(draft)
    assert len(GOLD_PEOPLE) == 11
    assert set(GOLD_PEOPLE) <= {row["name"] for row in public["characters"]}
    assert draft["extract"]["model_ran"] is True
    assert "接待室" in draft["current_scene"]
    _no_minor_copy(draft)


# U5 ---------------------------------------------------------------------------


def test_u5_preview_code_has_no_under18_gate_and_no_minor_copy():
    from app.services import context_presets as presets

    for fn in (presets.extract_preview_preset, presets.resolve_preview_aliases):
        assert "_avatar_is_under18" not in inspect.getsource(fn)
    for base in (ROOT / "backend" / "app", ROOT / "web" / "src"):
        for path in base.rglob("*"):
            if path.suffix in {".py", ".ts", ".tsx"}:
                assert MINOR_COPY not in path.read_text("utf-8"), path


def test_u5_this_module_opens_only_the_adult_gold():
    forbidden = "测试" + "长文本"
    own = Path(__file__).read_text("utf-8")
    assert forbidden not in own
    assert "open(" not in own.replace('"open("', "")
