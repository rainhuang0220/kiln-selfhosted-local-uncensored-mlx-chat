"""V12 hybrid: rules name harvest + clipped 9B identity fill (not whole corpus)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.providers.base import ChatChunk, ChatRequest

FIXTURE = (Path(__file__).parent / "fixtures" / "preset_ten_people.txt").read_text(encoding="utf-8")
PLANTED = [
    "祁律",
    "顾遥",
    "褚衡",
    "林夏",
    "阿沈",
    "沈知意",
    "方晏",
    "叶澄",
    "裴晚",
    "阮疏",
]
# Substrings of the planted identity sentences in the fixture.
PLANTED_IDENTITY_KW = {
    "祁律": ("室友", "大学"),
    "顾遥": ("同事", "前公司"),
    "褚衡": ("表哥",),
    "林夏": ("店员", "花店"),
    "阿沈": ("邻居",),
    "沈知意": ("管理员", "图书馆"),
    "方晏": ("同事",),
    "叶澄": ("助教", "画室"),
    "裴晚": ("店主", "咖啡"),
    "阮疏": ("同桌", "高中"),
}
UNIQUE_PHRASE = "橙花披肩在祁律肩上"
JUNK = ("湿透", "方先")


def _name_set(draft: dict) -> set[str]:
    return {str(c.get("name") or "") for c in draft.get("characters") or []}


def _identity_matches_planted(name: str, identity: str) -> bool:
    kws = PLANTED_IDENTITY_KW.get(name) or ()
    return any(kw in (identity or "") for kw in kws)


@pytest.mark.asyncio
async def test_h1_timeout_keeps_names_marks_pending(client):
    """H1: enrich never returns → names stay; 人物→待补; no junk names."""
    from app.services import context_presets as presets

    async def never_returns(source, draft, provider):
        await asyncio.sleep(3600)
        return draft

    with patch.object(presets, "deep_preview_preset", new=AsyncMock(side_effect=never_returns)):
        with patch("app.main.asyncio.wait_for", side_effect=TimeoutError):
            response = client.post(
                "/context/presets/preview",
                json={"text": FIXTURE, "deep": True},
            )
    assert response.status_code == 200
    draft = response.json()["draft"]
    names = _name_set(draft)
    assert len(names & set(PLANTED)) >= 8
    for junk in JUNK:
        assert junk not in names
    for row in draft["characters"]:
        ident = str(row.get("identity") or "")
        assert ident != "人物", row
        # Either honest 待补 or a real rules clause — never a blank fake fill.
        assert ident == "待补" or len(ident) >= 2


def test_h2_clip_for_window_not_whole_corpus():
    """H2: first-mention clip stays local and short."""
    from app.services.context_presets import clip_for

    corpus = (
        "顾遥那天在江边把披肩递给林晚。顾遥笑了笑。风很大。"
        "祁律是室友。" * 40
        + "褚衡是表哥。" * 40
        + "林夏是店员。" * 40
    )
    clip = clip_for("顾遥", corpus)
    assert "江边" in clip or "披肩" in clip
    assert len(clip) < 500
    # Must not swallow the padded paragraphs for other people.
    assert clip.count("祁律") <= 1
    assert "褚衡是表哥" not in clip or len(clip) < 200


@pytest.mark.asyncio
async def test_h3_fill_merge_uses_clipped_identity():
    """H3: merge fills identity from JSON, not just the bare name."""
    from app.services.context_presets import merge_people_extract, preview_preset

    draft = preview_preset(FIXTURE)
    # Strip to bare-name placeholders so merge must apply JSON.
    for row in draft["characters"]:
        if row["name"] == "顾遥":
            row["identity"] = "待补"
            row["one_event"] = None
    model_json = json.dumps(
        {
            "characters": [
                {"name": "顾遥", "identity": "前公司的同事", "one_event": "把钥匙放在桌上"},
            ]
        },
        ensure_ascii=False,
    )
    merged = merge_people_extract(FIXTURE, draft, model_json)
    gu = next(c for c in merged["characters"] if c["name"] == "顾遥")
    assert "同事" in gu["identity"] or "钥匙" in (gu.get("one_event") or "")
    assert gu["identity"] != "顾遥"


def test_h4_stub_fill_from_clips_hits_planted_identities():
    """H4: merge path (stub JSON from clips) locks ≥8 planted identity keywords."""
    from app.services.context_presets import (
        clip_for,
        harvest_people_from_corpus,
        merge_people_extract,
        preview_preset,
    )
    from app.services.style_bank import split_style_corpus

    draft = preview_preset(FIXTURE)
    split = split_style_corpus(FIXTURE)
    names = [c["name"] for c in harvest_people_from_corpus(split.corpus)]
    # Stub "9B": for each harvested name, pick identity keywords from its clip.
    chars = []
    for name in names:
        if name not in PLANTED_IDENTITY_KW:
            continue
        clip = clip_for(name, split.corpus)
        kws = PLANTED_IDENTITY_KW[name]
        # Prefer a keyword that actually appears in the clip.
        hit = next((kw for kw in kws if kw in clip), kws[0])
        # Reconstruct a short identity clause as the model would.
        identity = next(
            (
                line
                for line in clip.replace("。", "。\n").split("\n")
                if name in line and hit in line
            ),
            f"{hit}",
        )
        # Trim to a role clause around the keyword.
        if "是" in identity:
            identity = identity.split("是", 1)[-1].strip("。；;，, ")[:40]
        chars.append({"name": name, "identity": identity[:40], "one_event": ""})
    stub = json.dumps({"characters": chars}, ensure_ascii=False)
    # Start from names-only so merge must apply stub identities.
    bare = preview_preset(FIXTURE)
    for row in bare["characters"]:
        row["identity"] = "待补"
        row["one_event"] = None
    merged = merge_people_extract(FIXTURE, bare, stub)
    matched = sum(
        1
        for c in merged["characters"]
        if c["name"] in PLANTED_IDENTITY_KW
        and _identity_matches_planted(c["name"], c.get("identity") or "")
    )
    assert matched >= 8, [
        (c["name"], c.get("identity"))
        for c in merged["characters"]
        if c["name"] in PLANTED_IDENTITY_KW
    ]


@pytest.mark.asyncio
async def test_h5_live_clipped_enrich_within_50s():
    """H5: live semantic preview fits public proxy budget and keeps identities."""
    import httpx

    try:
        models = httpx.get("http://127.0.0.1:8081/v1/models", timeout=2.0)
        models.raise_for_status()
        probe = httpx.post(
            "http://127.0.0.1:8081/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "好"}],
                "max_tokens": 8,
                "temperature": 0.1,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=15.0,
        )
        if probe.status_code != 200 or not (probe.text or "").strip():
            raise RuntimeError("empty probe")
    except Exception:
        # One kickstart attempt, then skip if still dead.
        import subprocess

        uid = os.getuid()
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{uid}/com.kiln.mlx"],
            check=False,
            capture_output=True,
        )
        await asyncio.sleep(4)
        try:
            models = httpx.get("http://127.0.0.1:8081/v1/models", timeout=2.0)
            models.raise_for_status()
        except Exception:
            pytest.skip("MLX probe dead after one kickstart")

    from app.config import Settings
    from app.providers.mlx import MlxProvider
    from app.services.context_presets import deep_preview_preset, preview_preset

    provider = MlxProvider(Settings(mlx_base_url="http://127.0.0.1:8081"))
    draft = preview_preset(FIXTURE)
    # Clear identities so the test measures fill quality, not rules leftovers.
    for row in draft["characters"]:
        row["identity"] = "待补"
        row["one_event"] = None
    t0 = asyncio.get_event_loop().time()
    try:
        enriched = await asyncio.wait_for(
            deep_preview_preset(FIXTURE, draft, provider),
            timeout=50,
        )
    except TimeoutError:
        await provider.aclose()
        pytest.fail("semantic preview exceeded the 50s public proxy budget")
    except Exception as exc:
        await provider.aclose()
        pytest.fail(f"clipped enrich failed: {exc}")
    finally:
        await provider.aclose()
    elapsed = asyncio.get_event_loop().time() - t0
    assert elapsed <= 50, elapsed
    matched = 0
    non_pending = 0
    for c in enriched["characters"]:
        ident = str(c.get("identity") or "")
        if ident and ident not in ("待补", "人物", c["name"]):
            non_pending += 1
        if c["name"] in PLANTED_IDENTITY_KW and _identity_matches_planted(c["name"], ident):
            matched += 1
    assert non_pending >= 6, [
        (c["name"], c.get("identity")) for c in enriched["characters"]
    ]
    assert matched >= 6, [
        (c["name"], c.get("identity")) for c in enriched["characters"]
    ]
    assert "橙花披肩" not in (enriched.get("current_scene") or "")
    assert "顾客" in (enriched["me"]["identity"] or "")


@pytest.mark.asyncio
async def test_h6_chat_send_still_skips_enrich(chat_service, fake_provider):
    """H6: chat send must not call deep enrich."""
    extract_calls: list[int] = []

    async def spy_deep(*_a, **_k):
        extract_calls.append(1)
        raise AssertionError("LLM extract must not run on chat send")

    async def stream(request: ChatRequest):
        fake_provider.calls.append(request)
        yield ChatChunk(id="c1", model="fake", delta_content="好。")
        yield ChatChunk(
            id="c1", model="fake", finish_reason="stop", prompt_tokens=8, completion_tokens=2
        )
        yield ChatChunk(id="c1", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]
    with patch(
        "app.services.context_presets.deep_preview_preset",
        new=AsyncMock(side_effect=spy_deep),
    ):
        events = [
            ev
            async for ev in chat_service.chat(
                message=FIXTURE,
                conversation_id=None,
                stream=True,
                profile="immersive",
                auto_continue=False,
                max_tokens=64,
                owner_id="user-a",
            )
        ]
    assert extract_calls == []
    assert events
