"""V18: long-paste preview runs the 9B extract first, then rules ground every field."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

DOCS = Path(__file__).resolve().parents[2] / "docs" / "test"
FIXTURES = Path(__file__).parent / "fixtures"
WOVEN = (DOCS / "多人物交织场景_输入.md").read_text("utf-8")
GOLD = json.loads((DOCS / "多人物交织场景_标准结构.json").read_text("utf-8"))
TEN = (FIXTURES / "preset_ten_people.txt").read_text("utf-8")
SHARED = (FIXTURES / "preset_shared_scene_ten.txt").read_text("utf-8")

NARRATOR = GOLD["narrator"]
GOLD_PEOPLE = [p["name"] for p in GOLD["people"] if p["name"] != NARRATOR]
BLOCKLIST = {
    "他", "她", "你", "我", "姐姐", "哥哥", "妹妹", "弟弟", "妈妈", "爸爸", "母亲", "父亲",
    "宝宝", "主人", "小姐", "老师", "队长", "校医", "闺蜜", "学姐", "顾客", "技师",
}
TEN_PEOPLE = {"祁律", "顾遥", "褚衡", "林夏", "阿沈", "沈知意", "方晏", "叶澄", "裴晚", "阮疏", "岑照"}
# name → (identity must contain one of, identity must contain none of)
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


def _stub(payload: dict | list[dict], order: list[str] | None = None):
    calls: list = []
    payloads = payload if isinstance(payload, list) else [payload]

    async def complete(request):
        if order is not None:
            order.append("stage_a")
        calls.append(request)
        body = payloads[min(len(calls) - 1, len(payloads) - 1)]
        return SimpleNamespace(content=json.dumps(body, ensure_ascii=False))

    complete.calls = calls
    return complete


def _raising(exc: Exception):
    calls: list = []

    async def complete(request):
        calls.append(request)
        raise exc

    complete.calls = calls
    return complete


def _public(draft):
    from app.services.context_presets import public_studio_payload

    return public_studio_payload(draft)


def _identities(public) -> dict[str, str]:
    return {row["name"]: row["identity"] for row in public["characters"]}


def _gold_people() -> list[dict]:
    """Gold name + short identity pairs (not the 300–400 字 narratives)."""
    people = []
    for person in GOLD["people"]:
        aliases = ["姐姐"] if person["name"] == "陆遥" else []
        people.append({
            "name": person["name"],
            "aliases": aliases,
            "identity": person["identity"],
            "one_event": "",
            "present": person["name"] in {"许澄", NARRATOR},
        })
    return people


async def _extract(source: str, complete):
    from app.services.context_presets import extract_preview_preset

    return await extract_preview_preset(source, None, complete=complete)


# M1 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m1_stage_a_runs_before_any_rules_roster():
    from app.services import context_presets as presets

    order: list[str] = []
    real_harvest = presets.harvest_people_from_corpus

    def spy_harvest(corpus):
        order.append("harvest")
        return real_harvest(corpus)

    stub = _stub({"people": [{"name": "陆遥", "aliases": ["姐姐"], "identity": "陆闻的姐姐"}]}, order)
    with patch.object(presets, "harvest_people_from_corpus", side_effect=spy_harvest):
        draft = await _extract(WOVEN, stub)
    assert order and order[0] == "stage_a"
    assert "harvest" not in order
    public = _public(draft)
    ids = _identities(public)
    assert "陆遥" in ids and "姐姐" in ids["陆遥"]
    # Last-chance scan may add 蒋越 (蒋越二十八岁); it may never add an alias.
    assert "蒋越" in ids
    assert not (set(ids) & BLOCKLIST)
    assert draft["extract"]["mode"] == "model"
    assert "蒋越" in draft["extract"]["last_chance"]


# M2 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m2_identity_the_source_did_not_attach_is_dropped():
    stub = _stub({"people": [
        {"name": "唐宁", "aliases": [], "identity": "校医", "one_event": ""},
        {"name": "周岚", "aliases": [], "identity": "排球队长", "one_event": ""},
        {"name": "蒋越", "aliases": [], "identity": "负责收球", "one_event": ""},
    ]})
    ids = _identities(_public(await _extract(WOVEN, stub)))
    assert "校医" not in ids["唐宁"]
    assert "队长" not in ids["周岚"] and "排球" not in ids["周岚"]
    assert ids["蒋越"] == "负责收球"


# M3 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m3_alias_and_role_rows_never_become_people():
    stub = _stub({"people": [
        {"name": token, "aliases": [], "identity": "人物"} for token in sorted(BLOCKLIST)
    ] + [{"name": "陆遥", "aliases": ["姐姐"], "identity": "姐姐"}]})
    draft = await _extract(WOVEN, stub)
    public = _public(draft)
    names = set(_identities(public))
    assert not (names & BLOCKLIST)
    assert "陆遥" in names
    for event in public["timeline"]:
        assert not (set(event["who"]) & BLOCKLIST)


# M4 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m4_gold_pairs_survive_grounding_with_source_true_identities():
    draft = await _extract(WOVEN, _stub({"people": _gold_people()}))
    public = _public(draft)
    ids = _identities(public)
    assert set(GOLD_PEOPLE) <= set(ids), sorted(ids)
    assert NARRATOR not in ids
    assert not (set(ids) & BLOCKLIST)
    crossed = []
    for name, (need, never) in TABLE.items():
        identity = ids[name]
        if not any(token in identity for token in need) or any(token in identity for token in never):
            crossed.append((name, identity))
    assert not crossed, crossed
    assert "接待室" in public["current_scene"]
    assert "陆遥" not in public["current_scene"]
    assert "顾客" in public["me"]["identity"]
    blob = json.dumps(public, ensure_ascii=False)
    for token in ("needs_review", "suggested_who", "source_span", "segments", "\"type\""):
        assert token not in blob


@pytest.mark.asyncio
async def test_m4_recorded_live_windows_ground_without_crossing():
    """Raw 9B answers recorded from :8081 on the woven diary, replayed through Stage B."""
    recorded = json.loads((FIXTURES / "v18_stage_a_woven_live.json").read_text("utf-8"))["windows"]

    async def complete(request):
        part = int(re.search(r'part="(\d+)/', request.messages[-1]["content"]).group(1))
        return SimpleNamespace(content=recorded[part - 1])

    public = _public(await _extract(WOVEN, complete))
    ids = _identities(public)
    assert set(GOLD_PEOPLE) <= set(ids), sorted(ids)
    wrong = [
        (name, ids[name]) for name, (need, never) in TABLE.items()
        if not any(token in ids[name] for token in need) or any(token in ids[name] for token in never)
    ]
    assert not wrong, wrong


# M5 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m5_stage_a_reads_reference_paragraphs_not_clips():
    from app.services.context_compiler.extract import EXTRACT_SYSTEM
    from app.services.style_bank import split_style_corpus

    stub = _stub({"people": []})
    await _extract(WOVEN, stub)
    assert len(stub.calls) == 2
    corpus = split_style_corpus(WOVEN.strip()).corpus
    bodies = []
    for request in stub.calls:
        assert request.messages[0] == {"role": "system", "content": EXTRACT_SYSTEM}
        assert request.enable_thinking is False
        assert request.temperature == 0.0
        assert request.max_tokens <= 1200
        user = request.messages[-1]["content"]
        live = re.search(r"<live>(.*?)</live>", user, re.S).group(1)
        assert len(live) <= 200 and "许澄" in live
        body = re.search(r"<reference[^>]*>\n(.*)\n</reference>", user, re.S).group(1)
        assert 1200 <= len(body) <= 1800, len(body)
        assert body in corpus
        assert " :: " not in user
        bodies.append(body)
    assert any("唐宁让我重新站到发球线" in body for body in bodies)
    for sentence in re.split(r"(?<=[。！？])", corpus):
        sentence = sentence.strip()
        if sentence:
            assert any(sentence in body for body in bodies), sentence[:30]


def test_m5_window_geometry():
    from app.services.context_compiler.extract import reference_windows

    text = "".join(f"第{i}句话里有一些人物和事情发生。" for i in range(400))
    windows = reference_windows(text)
    assert len(windows) >= 3
    for window in windows[:-1]:
        assert 1200 <= len(window) <= 1800
    for left, right in zip(windows, windows[1:]):
        assert left[-150:] in right or right[:150] in left
    assert reference_windows("短文。") == ["短文。"]


# M6 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m6_invented_name_is_dropped():
    stub = _stub({"people": [
        {"name": "赵敏", "aliases": ["姐姐"], "identity": "陆闻的姐姐", "one_event": "赵敏翻开册子"},
        {"name": "陆遥", "aliases": ["姐姐"], "identity": "姐姐"},
    ]})
    draft = await _extract(WOVEN, stub)
    names = set(_identities(_public(draft)))
    assert "赵敏" not in names
    assert "陆遥" in names
    assert "赵敏" in draft["extract"]["dropped"]


# M7 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m7_default_hop_stays_in_parlor_and_named_recall_works():
    from app.services.context_compiler import route_context

    woven = await _extract(WOVEN, _stub({"people": _gold_people()}))
    hop = route_context(woven["context_ir"], "你好")
    assert "陆遥" not in hop.fence
    recall = route_context(woven["context_ir"], "陆遥那天说了什么？")
    assert "陆遥" in (recall.reference_fence or recall.fence)

    shared = await _extract(SHARED, _stub({"people": [
        {"name": name, "aliases": [], "identity": ""} for name in sorted(TEN_PEOPLE)
    ]}))
    hop = route_context(shared["context_ir"], "你好")
    assert "阁楼" not in hop.fence
    assert "顾遥" not in hop.fence


# M8 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m8_v17_fixtures_still_hold():
    from app.services.context_presets import preview_preset

    assert len(set(_identities(_public(preview_preset(TEN)))) & TEN_PEOPLE) >= 10
    ten = await _extract(TEN, _stub({"people": [
        {"name": name, "aliases": [], "identity": ""} for name in sorted(TEN_PEOPLE)
    ]}))
    public = _public(ten)
    assert len(set(_identities(public)) & TEN_PEOPLE) >= 10
    assert "顾客" in public["me"]["identity"]

    shared = await _extract(SHARED, _stub({"people": [
        {"name": name, "aliases": [], "identity": ""} for name in sorted(TEN_PEOPLE)
    ]}))
    timeline = _public(shared)["timeline"]
    assert any({"顾遥", "褚衡", "林夏"} <= set(event["who"]) for event in timeline)


# M9 ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m9_chat_send_never_runs_stage_a(chat_service, fake_provider):
    from app.services import context_presets as presets

    with patch.object(presets, "run_stage_a", new=AsyncMock()) as stage_a:
        with patch.object(presets, "extract_preview_preset", new=AsyncMock()) as extract:
            events = [
                event
                async for event in chat_service.chat(
                    message=WOVEN,
                    conversation_id=None,
                    stream=True,
                    profile="immersive",
                    auto_continue=False,
                    max_tokens=64,
                    owner_id="owner-v18",
                )
            ]
    assert not [event for event in events if event.get("event") == "error"]
    stage_a.assert_not_called()
    extract.assert_not_called()
    assert all("人物资料编译器" not in str(call.messages) for call in fake_provider.calls)


# M10 --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m10_stage_a_failure_falls_back_to_rules_without_alias_rows():
    stub = _raising(TimeoutError("mlx timeout"))
    draft = await _extract(WOVEN, stub)
    assert len(stub.calls) == 2
    assert draft["extract"]["mode"] == "rules_fallback"
    public = _public(draft)
    names = set(_identities(public))
    assert not (names & BLOCKLIST)
    assert {"陆遥", "沈乔", "蒋越", "顾青"} <= names
    assert any("规则预览" in note for note in public.get("uncertain") or [])


def test_m10_endpoint_survives_stage_a_error(client):
    from app.services import context_presets as presets

    with patch.object(presets, "run_stage_a", new=AsyncMock(side_effect=RuntimeError("mlx error 401"))):
        response = client.post("/context/presets/preview", json={"text": WOVEN, "deep": True})
    assert response.status_code == 200
    draft = response.json()["draft"]
    names = {row["name"] for row in draft["characters"]}
    assert not (names & BLOCKLIST)
    assert {"陆遥", "蒋越", "顾青"} <= names
    blob = json.dumps(draft, ensure_ascii=False)
    for token in ("needs_review", "suggested_who", "source_span", "segments", "extract"):
        assert token not in blob


def test_m10_endpoint_long_paste_uses_extract_short_paste_does_not(client):
    from app.services import context_presets as presets

    real = presets.extract_preview_preset
    with patch.object(presets, "extract_preview_preset", new=AsyncMock(side_effect=real)) as extract:
        long = client.post("/context/presets/preview", json={"text": WOVEN, "deep": True})
        assert long.status_code == 200
        assert extract.await_count == 1
        short = client.post(
            "/context/presets/preview",
            json={"text": "你是技师许澄。我是顾客。姐姐陆遥说过一句话。", "deep": True},
        )
        assert short.status_code == 200
        assert extract.await_count == 1


# M11 (optional live) ----------------------------------------------------------


@pytest.mark.skipif(os.environ.get("KILN_LIVE_V18") != "1", reason="live Stage A is opt-in")
@pytest.mark.asyncio
async def test_m11_live_stage_a_on_woven_diary():
    import time

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
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
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

    started = time.monotonic()
    draft = await _extract(WOVEN, complete)
    elapsed = time.monotonic() - started
    public = _public(draft)
    ids = _identities(public)
    print(f"M11 elapsed={elapsed:.1f}s extract={draft.get('extract')}")
    for name, identity in ids.items():
        print(f"M11 {name}: {identity}")
    crossed = [
        (name, ids[name]) for name, (need, never) in TABLE.items()
        if name in ids and any(token in ids[name] for token in never)
    ]
    print(f"M11 crossed={crossed}")
    assert elapsed <= 90
    assert draft["extract"]["mode"] == "model"
    assert not (set(ids) & BLOCKLIST)
    assert len(crossed) < 3, crossed
