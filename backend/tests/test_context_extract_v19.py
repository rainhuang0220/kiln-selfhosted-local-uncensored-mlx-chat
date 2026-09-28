"""V19: a long-paste preview the 9B did not analyze fails visibly; no silent rules roster."""

from __future__ import annotations

import inspect
import json
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

DOCS = Path(__file__).resolve().parents[2] / "docs" / "test"
WOVEN = (DOCS / "多人物交织场景_输入.md").read_text("utf-8")
GOLD = json.loads((DOCS / "多人物交织场景_标准结构.json").read_text("utf-8"))
NARRATOR = GOLD["narrator"]
GOLD_PEOPLE = [p["name"] for p in GOLD["people"] if p["name"] != NARRATOR]
BLOCKLIST = {
    "他", "她", "你", "我", "姐姐", "哥哥", "妹妹", "弟弟", "妈妈", "爸爸", "母亲", "父亲",
    "宝宝", "主人", "小姐", "老师", "队长", "校医", "闺蜜", "学姐", "顾客", "技师",
}
RETRY_COPY = "模型没有分析，请重试。没有使用规则名册。"
TABLE = {
    "许澄": (("技师",), ("顾客", "姐姐")),
    "陆遥": (("姐姐",), ("闺蜜", "队长", "校医")),
    "沈乔": (("闺蜜",), ("姐姐", "队长")),
    "唐宁": (("队长", "排球"), ("校医", "店员")),
    "蒋越": (("收球", "队员"), ("队长",)),
    "周岚": (("校医", "咨询"), ("队长", "排球")),
    "林见": (("店员", "林栀的姐姐"), ("地铁职员",)),
    "林栀": (("妹妹",), ("店长",)),
    "何冉": (("办公", "工牌", "聚会"), ("线路图", "画线路")),
    "叶舒": (("同事", "线路"), ("打电话",)),
    "顾青": (("同学",), ("店员",)),
}


def _stub(payload: dict):
    calls: list = []

    async def complete(request):
        calls.append(request)
        return SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))

    complete.calls = calls
    return complete


def _gold_people() -> list[dict]:
    return [
        {
            "name": person["name"],
            "aliases": ["姐姐"] if person["name"] == "陆遥" else [],
            "identity": person["identity"],
            "one_event": "",
            "present": person["name"] in {"许澄", NARRATOR},
        }
        for person in GOLD["people"]
    ]


def _public(draft):
    from app.services.context_presets import public_studio_payload

    return public_studio_payload(draft)


def _ids(public) -> dict[str, str]:
    return {row["name"]: row["identity"] for row in public["characters"]}


async def _extract(source: str, complete):
    from app.services.context_presets import extract_preview_preset

    return await extract_preview_preset(source, None, complete=complete)


# F1 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_f1_no_runner_returns_empty_cards_not_a_rules_roster():
    from app.services import context_presets as presets

    harvested: list[str] = []
    real = presets.harvest_people_from_corpus

    def spy(corpus):
        harvested.append("harvest")
        return real(corpus)

    with patch.object(presets, "harvest_people_from_corpus", side_effect=spy):
        draft = await presets.extract_preview_preset(WOVEN, None)
    assert not harvested
    assert draft["extract"]["model_ran"] is False
    public = _public(draft)
    assert public["characters"] == []
    assert public["timeline"] == []
    assert public["extract"]["model_ran"] is False
    blob = json.dumps(public, ensure_ascii=False)
    assert "陆遥" not in blob and "唐宁" not in blob


@pytest.mark.asyncio
async def test_f1_stage_a_errors_return_empty_cards():
    calls: list = []

    async def boom(request):
        calls.append(request)
        raise RuntimeError("mlx error 401: Repository Not Found")

    draft = await _extract(WOVEN, boom)
    assert len(calls) == 2
    assert draft["extract"]["model_ran"] is False
    assert draft["extract"]["window_chars"] and all(n >= 800 for n in draft["extract"]["window_chars"])
    assert _public(draft)["characters"] == []


@pytest.mark.asyncio
async def test_f1_stage_a_prose_without_json_returns_empty_cards():
    async def prose(request):
        return SimpleNamespace(content="好的，我来分析一下这些人物。")

    draft = await _extract(WOVEN, prose)
    assert draft["extract"]["model_ran"] is False
    assert _public(draft)["characters"] == []


def test_f1_endpoint_never_fills_cards_from_rules(client, fake_provider):
    # FakeProvider echoes prose: Stage A runs, returns no people JSON.
    response = client.post("/context/presets/preview", json={"text": WOVEN, "deep": True})
    assert response.status_code == 200
    draft = response.json()["draft"]
    assert draft["characters"] == [] and draft["timeline"] == []
    assert draft["extract"]["model_ran"] is False
    assert draft["extract"]["mode"] == "model_failed"
    assert any("人物资料编译器" in str(call.messages) for call in fake_provider.calls)


def test_f1_endpoint_extract_exception_is_visible(client):
    from app.services import context_presets as presets

    async def explode(*_a, **_kw):
        raise ConnectionError("mlx unreachable")

    with patch.object(presets, "extract_preview_preset", side_effect=explode):
        response = client.post("/context/presets/preview", json={"text": WOVEN, "deep": True})
    assert response.status_code == 200
    draft = response.json()["draft"]
    assert draft["characters"] == []
    assert draft["extract"]["model_ran"] is False


def test_f1_endpoint_busy_chat_is_visible(client, chat_service):
    chat_service._busy.add("other-conversation")
    try:
        response = client.post("/context/presets/preview", json={"text": WOVEN, "deep": True})
    finally:
        chat_service._busy.discard("other-conversation")
    draft = response.json()["draft"]
    assert draft["characters"] == []
    assert draft["extract"] == {**draft["extract"], "model_ran": False, "mode": "busy"}


def test_f1_no_rules_fallback_on_the_deep_path():
    from app import main
    from app.services import context_presets as presets

    assert "rules_fallback_preview" not in inspect.getsource(main)
    assert "rules_fallback_preview" not in inspect.getsource(presets.extract_preview_preset)
    assert not hasattr(presets, "rules_fallback_preview")


# F2 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_f2_adult_ages_do_not_trip_under18_and_stage_a_runs():
    from app.services.context_compiler.binder import _UNDER18, _avatar_is_under18
    from app.services.context_presets import _live_user_identity
    from app.services.style_bank import split_style_corpus

    source = WOVEN.strip()
    for token in ("二十九岁", "三十二岁", "小一岁"):
        assert token in source
    assert _UNDER18.search(source) is None
    avatar = _live_user_identity(split_style_corpus(source).live.strip())
    assert _avatar_is_under18(source, {"me": {"identity": avatar}}) is False
    stub = _stub({"people": []})
    await _extract(WOVEN, stub)
    assert len(stub.calls) == 2


# F3 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_f3_success_is_stamped_with_model_ran_elapsed_and_windows():
    draft = await _extract(WOVEN, _stub({"people": _gold_people()}))
    meta = draft["extract"]
    assert meta["mode"] == "model"
    assert meta["model_ran"] is True
    assert isinstance(meta["elapsed_s"], float)
    assert len(meta["window_chars"]) == 2
    assert all(n >= 800 for n in meta["window_chars"])
    public = _public(draft)
    assert public["extract"]["model_ran"] is True
    ids = _ids(public)
    assert set(GOLD_PEOPLE) <= set(ids)
    assert not (set(ids) & BLOCKLIST)
    crossed = [
        (name, ids[name]) for name, (need, never) in TABLE.items()
        if not any(t in ids[name] for t in need) or any(t in ids[name] for t in never)
    ]
    assert not crossed, crossed


def test_f3_endpoint_payload_carries_the_stamp(client, fake_provider):
    stub = _stub({"people": _gold_people()})
    fake_provider.complete = stub
    response = client.post("/context/presets/preview", json={"text": WOVEN, "deep": True})
    assert response.status_code == 200
    draft = response.json()["draft"]
    assert draft["extract"]["model_ran"] is True
    assert draft["extract"]["mode"] == "model"
    assert all(n >= 800 for n in draft["extract"]["window_chars"])
    assert set(GOLD_PEOPLE) <= {row["name"] for row in draft["characters"]}
    blob = json.dumps(draft, ensure_ascii=False)
    for token in ("needs_review", "suggested_who", "source_span", "segments", "context_ir", "errors"):
        assert token not in blob


# F4 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_f4_grounding_only_subtracts():
    stub = _stub({"people": [
        {"name": "唐宁", "aliases": [], "identity": "校医", "one_event": ""},
        {"name": "周岚", "aliases": [], "identity": "校医", "one_event": ""},
    ]})
    draft = await _extract(WOVEN, stub)
    public = _public(draft)
    ids = _ids(public)
    assert "校医" not in ids.get("唐宁", "")
    assert ids.get("唐宁", "") in {"", "待补"}
    assert "校医" in ids["周岚"]
    # Names the model did not propose are not added by a rules scan.
    assert set(ids) <= {"唐宁", "周岚", "许澄"}
    # The grounder adds no event; the binder may attach clauses of a bound source beat.
    flat = re.sub(r"\s+", "", WOVEN)
    for row in public["characters"]:
        for clause in re.split(r"[，,。；;！？]", row.get("one_event") or ""):
            assert re.sub(r"\s+", "", clause) in flat, (row["name"], clause)


# F5 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_f5_default_hop_stays_in_the_parlor():
    from app.services.context_compiler import route_context

    draft = await _extract(WOVEN, _stub({"people": _gold_people()}))
    assert "接待室" in draft["current_scene"]
    hop = route_context(draft["context_ir"], "你好")
    assert "陆遥" not in hop.fence


# F6 ---------------------------------------------------------------------------


def test_f6_short_paste_stays_rules_short_and_fast(client, fake_provider):
    text = ("你是技师许澄。我是顾客。姐姐陆遥说过一句话。" * 10)[:200]
    started = time.monotonic()
    response = client.post("/context/presets/preview", json={"text": text, "deep": True})
    assert time.monotonic() - started < 3
    assert response.status_code == 200
    draft = response.json()["draft"]
    assert draft["extract"]["mode"] == "rules_short"
    assert draft["extract"]["model_ran"] is False
    assert not fake_provider.calls


# F7 ---------------------------------------------------------------------------


def test_f7_failure_payload_is_what_studio_needs_for_the_retry_copy(client):
    response = client.post("/context/presets/preview", json={"text": WOVEN, "deep": True})
    draft = response.json()["draft"]
    # Studio renders RETRY_COPY when model_ran is false on a non-short paste.
    assert draft["extract"]["model_ran"] is False
    assert draft["extract"]["mode"] != "rules_short"
    assert draft["characters"] == []
    web = Path(__file__).resolve().parents[2] / "web" / "src"
    assert RETRY_COPY in (web / "api" / "context-presets.ts").read_text("utf-8")
    studio = (web / "components" / "ContextPresetStudio.tsx").read_text("utf-8")
    assert "MODEL_DID_NOT_ANALYZE" in studio and "模型已分析" in studio


# F8 (optional live) -----------------------------------------------------------


@pytest.mark.skipif(os.environ.get("KILN_LIVE_V19") != "1", reason="live Stage A is opt-in")
@pytest.mark.asyncio
async def test_f8_live_floor_on_woven_diary():
    import httpx

    base = "http://127.0.0.1:8081/v1"
    try:
        model_id = httpx.get(f"{base}/models", timeout=5.0).json()["data"][0]["id"]
        probe = httpx.post(f"{base}/chat/completions", timeout=30.0, json={
            "model": model_id,
            "messages": [{"role": "user", "content": "只回一个字：好"}],
            "max_tokens": 8,
            "chat_template_kwargs": {"enable_thinking": False},
        })
        content = probe.json()["choices"][0]["message"]["content"]
    except Exception as exc:  # never restart MLX from a test
        pytest.skip(f"path-id probe is not a real completion: {exc}")
    if probe.status_code != 200 or not (content or "").strip():
        pytest.skip("path-id probe is not a real completion")

    async def complete(request):
        async with httpx.AsyncClient(timeout=90.0, trust_env=False) as client:
            response = await client.post(f"{base}/chat/completions", json={
                "model": model_id,
                "messages": request.messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "top_k": request.top_k,
                "max_tokens": request.max_tokens,
                "chat_template_kwargs": {"enable_thinking": request.enable_thinking},
            })
        response.raise_for_status()
        return SimpleNamespace(content=response.json()["choices"][0]["message"]["content"] or "")

    draft = await _extract(WOVEN, complete)
    meta = draft["extract"]
    public = _public(draft)
    ids = _ids(public)
    print(f"F8 extract={meta}")
    for name, identity in ids.items():
        print(f"F8 {name}: {identity}")
    if not meta["model_ran"]:
        assert public["characters"] == []
        return
    assert meta["elapsed_s"] >= 20, meta
    assert not (set(ids) & BLOCKLIST)
