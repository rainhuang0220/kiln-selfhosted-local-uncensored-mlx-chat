"""Night V23: paragraph-cycle loop guard and immersive repetition floor."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
# Cycle shape from a live 9B fill hop: short questions + 括号 lines, no ≥16-char sentence back-to-back.
_OPEN = "（轻轻拉上门帘，把热毛巾推到你面前）\n\n晚上好，先润润嗓子，毛巾也是温热的，待会儿擦擦脸。\n\n"
_CYCLE = (
    "您看，现在打算先从哪里开始？是看看菜单，还是……想先聊聊心情？只要您点头，我这就安排。\n\n"
    "（稍作停顿，观察您的反应，等待您进一步指示）\n\n"
    "那您说呢？想先从哪里开始？只是别太紧张，放松点就好。\n\n"
    "（微微侧身，目光温和地等着您的下一步指示，随时准备配合）\n\n"
)


def test_paren_action_line_counts_as_a_sentence():
    from app.services.repetition import repeated_sentence_start

    line = "（稍作停顿，观察您的反应，等待您进一步指示）"
    text = f"{line}\n\n她笑了笑。\n\n{line}"
    assert repeated_sentence_start(text) == len(text) - len(line)
    assert repeated_sentence_start(f"{line}\n\n她笑了笑。") is None
    # Short inline stage directions may recur.
    assert repeated_sentence_start("（笑）好的。\n\n（笑）") is None


def test_tail_window_loop_cuts_paragraph_cycle_keeps_opening():
    from app.services.repetition import tail_window_loop

    text = _OPEN + _CYCLE * 6
    cut = tail_window_loop(text)
    assert cut is not None
    kept = text[:cut]
    assert kept.startswith(_OPEN.strip()[:10])
    assert kept.count("（稍作停顿，观察您的反应，等待您进一步指示）") <= 1
    assert len(kept) < len(_OPEN) + len(_CYCLE) + 10


def test_tail_window_loop_quiet_on_prose_fixtures():
    from app.services.repetition import tail_window_loop

    for name in ("preset_dense_adult_twelve.txt", "preset_shared_scene_ten.txt", "preset_ten_people.txt"):
        text = (FIXTURES / name).read_text("utf-8")
        for n in range(800, len(text), 40):
            assert tail_window_loop(text[:n]) is None, (name, n)


def _pieces(text: str) -> list[int]:
    # Toy tokenizer: 「聊天」 is one token, everything else one char per token.
    out, i = [], 0
    while i < len(text):
        if text.startswith("聊天", i):
            out.append(-1)
            i += 2
        else:
            out.append(ord(text[i]))
            i += 1
    return out


def _unpieces(ids: list[int]) -> str:
    return "".join("聊天" if t == -1 else chr(t) for t in ids)


def test_continue_prompt_never_lands_on_cached_prompt_minus_last_token():
    """Live V23 crash: hop 3 re-encoded to hop 2's ids minus one token (different string)."""
    from app.services.continuation import shorten_until_unused

    sent = "接待室里灯调暗了。你能陪我聊天"  # hop 2 prompt; mlx caches its ids minus the last token
    native = "接待室里灯调暗了。你能陪我呀"  # guard-trimmed hop 3 differs only in the last token
    prompt, tail = shorten_until_unused(native, encode=_pieces, decode=_unpieces, used=[sent])
    assert _pieces(prompt) != _pieces(sent)[:-1]
    assert _pieces(prompt) != _pieces(sent)
    assert prompt + tail == native
    # Without history the one-token drop is unchanged.
    assert shorten_until_unused(native, encode=_pieces, decode=_unpieces, used=[])[0] == "接待室里灯调暗了。你能陪我"


def _parlor_ir() -> dict:
    from app.services.context_presets import chat_frame_from_simple, preview_preset

    source = (FIXTURES / "overnight_wenai_parlor.txt").read_text("utf-8")
    return chat_frame_from_simple(preview_preset(source), source_text=source)["context_ir"]


def test_default_hop_keeps_only_explicit_short_bracket_preferences():
    from app.services.context_compiler import route_context

    for message in ("你好", "你靠近一点"):
        fence = route_context(_parlor_ir(), message).fence
        assert "技师" in fence and "接待室" in fence
        assert fence.splitlines()[-1].startswith("此刻现场：")
        assert "称呼：叫我“客人”" in fence
        assert "不要做：不介绍房间陈设" in fence
        assert "<style_digest" not in fence and "<service_requirements" not in fence
        assert "呼吸、指尖温度" not in fence
        assert len(fence) <= 281
        assert "陆遥" not in fence


def test_style_digest_drops_named_and_memory_lines_and_skips_recall():
    from app.services.context_compiler import route_context

    ir = _parlor_ir()
    ir["entities"] = [{"name": "陆遥", "identity": "姐姐"}]
    ir["segments"] = [
        *ir["segments"],
        {"type": "UNKNOWN", "scope": "reference", "needs_review": True, "text": "（称呼：像陆遥那样叫我）"},
        {"type": "UNKNOWN", "scope": "reference", "needs_review": True, "text": "（那天：她在门口等了很久）"},
        {"type": "UNKNOWN", "scope": "reference", "needs_review": True, "text": "（她慢慢走过来，说今晚很长）"},
        {"type": "EVENT", "scope": "reference", "text": "（节奏：陆遥的节奏）"},
    ]
    fence = route_context(ir, "你好").fence
    assert "陆遥" not in fence
    assert "那天" not in fence
    assert "今晚很长" not in fence
    recall = route_context(ir, "陆遥是谁")
    assert recall.intent == "recall"
    assert "<style_digest" not in recall.fence


def test_grounded_contract_uses_the_short_scene_instruction():
    from app.services.literary_system import GROUNDED_CONTEXT_SYSTEM

    assert "先接上一句用户输入" in GROUNDED_CONTEXT_SYSTEM
    assert "此刻现场" in GROUNDED_CONTEXT_SYSTEM
    assert "角色演员" not in GROUNDED_CONTEXT_SYSTEM


def test_next_beat_hint_moves_scene_and_forbids_reasking():
    from app.services.scene_graph import next_beat_hint

    asked = next_beat_hint("（指尖搭在你手腕上）\n\n客人，是想要个安静的夜，还是让我陪你说说话？")
    assert "不要再提问" in asked
    assert "不要重复" in asked
    assert "客人" not in asked
    calm = next_beat_hint("（她把毛巾展开，搭在你肩上。）")
    assert "不要再提问" not in calm


@pytest.mark.asyncio
async def test_fill_hop_fence_carries_next_beat(require_chat_template, chat_service, fake_provider):
    events = [e async for e in chat_service.chat(
        message="你好",
        conversation_id=None,
        stream=True,
        profile="immersive",
        auto_continue=True,
        max_tokens=64,
    )]
    assert not [e for e in events if e.get("event") == "error"]
    calls = fake_provider.calls
    if len(calls) < 2:
        pytest.skip("fake provider reached the floor in one hop")
    first = "\n".join(m.get("content") or "" for m in calls[0].messages)
    later = "\n".join(m.get("content") or "" for m in calls[1].messages)
    assert "<next_beat>" not in first
    assert "<next_beat>" in later


# Slot-filled template from a live cycle-5 hop: no ≥16-char sentence repeats verbatim.
_REFRAIN = (
    "（伸手轻轻整理了一下你肩头的衣物，动作细致而体贴）\n衣服也整理一下，这样更舒服。\n"
    "（另一只手顺势抚过你的手臂，感受肌肤的温度和质感）\n手臂也放松一下，感觉是不是更轻松了？\n"
    "（身体微微前倾，几乎贴近你的背部，感受背部的线条）\n背部也放松一下，看看能有多松。\n"
    "（手臂再次轻轻抬起，这次动作更加流畅而自然）\n手臂再放松一下，感觉是不是更轻盈了？\n"
)


def test_refrain_run_cuts_slot_template_and_keeps_first_line():
    from app.services.repetition import refrain_run_start

    cut = refrain_run_start(_REFRAIN)
    assert cut is not None
    kept = _REFRAIN[:cut]
    assert "手臂也放松一下" in kept
    assert "背部也放松一下" not in kept


def test_refrain_run_cuts_option_menu():
    from app.services.repetition import refrain_run_start

    menu = (
        "（她把门帘放下，指尖拂过矮桌上的温水杯）\n“水温刚好，您先润润嗓子。”\n"
        "（她把毛巾放下，笑着看你）\n“客人，今晚想怎么安排呢？”\n\n**下一步行动提示：**\n"
        "- **选项 A**：如果您想看菜单或服务项目介绍。\n"
        "- **选项 B**：如果您想直接说明需求或想要的项目。\n"
        "- **选项 C**：如果您想先了解环境或氛围。\n"
    )
    cut = refrain_run_start(menu)
    assert cut is not None
    assert "选项 B" not in menu[:cut]


def test_refrain_run_quiet_on_prose_fixtures():
    from app.services.repetition import refrain_run_start

    for name in ("preset_dense_adult_twelve.txt", "preset_shared_scene_ten.txt"):
        text = (FIXTURES / name).read_text("utf-8")
        for n in range(1, len(text) + 1):
            assert refrain_run_start(text[:n]) is None, (name, n)


def test_repeated_sentence_start_sees_previous_reply():
    from app.services.repetition import repeated_sentence_start

    prior = "（手臂微微用力，将整个手臂的重量轻轻靠在你的肩膀上，感受你的反应）\n就这样。"
    text = "（侧身向你走近两步，围裙系带轻轻晃）\n好，那再靠近一点。\n（手臂微微用力，将整个手臂的重量轻轻靠在你的肩膀上，感受你的反应）"
    start = repeated_sentence_start(text, prior=prior)
    assert start is not None and text[start:].startswith("（手臂微微用力")
    assert repeated_sentence_start(text) is None
    assert repeated_sentence_start("好，那再靠近一点。", prior="好，那再靠近一点。") is None


def test_repeated_line_start_catches_short_refrain_lines():
    from app.services.repetition import repeated_line_start

    text = "“只要一声，我就在。”\n\n（指尖勾住你衣领）\n\n“只要一声，我就在。”"
    start = repeated_line_start(text)
    assert start is not None and text[start:].startswith("“只要一声")
    assert repeated_line_start("“我在呢。”\n\n（笑）\n\n“我在呢。”") is None
    assert repeated_line_start("（她把毛巾递过来）\n“我就在这儿，陪着您。”", prior="“我就在这儿……陪着您。”") is not None


def _noise(n: int, tag: str) -> str:
    import random

    rng = random.Random(tag)
    parts: list[str] = []
    while sum(len(p) for p in parts) < n:
        body = "".join(chr(rng.randint(0x4E00, 0x9FA5)) for _ in range(16))
        parts.append(f"{tag}{len(parts)}{body}。")
    return "".join(parts)


@pytest.mark.asyncio
async def test_short_immersive_reply_does_not_force_fill_hops(chat_service, fake_provider, monkeypatch):
    from app.providers.base import ChatChunk, ChatRequest

    copied = "（手臂微微用力，将整个手臂的重量轻轻靠在你的肩膀上，感受你的反应）"
    first_reply = _noise(300, "旧") + "\n" + copied + "\n"
    opening = _noise(900, "新")
    calls = {"n": 0}

    monkeypatch.setattr(
        chat_service.tokenizer, "continuation_completion_prompt", lambda messages, **kw: ("CONT", "")
    )
    monkeypatch.setattr(chat_service.tokenizer, "special_token_ids", lambda names: [7], raising=False)
    monkeypatch.setattr(chat_service.tokenizer, "first_token", lambda text: None, raising=False)

    async def stream(request: ChatRequest):
        calls["n"] += 1
        if calls["n"] == 1:
            body = first_reply
        elif calls["n"] == 2:
            body = opening
        elif calls["n"] == 3:
            body = ["\n" + copied, "\n" + _noise(200, "抄")]
        else:
            body = _noise(4200, f"续{calls['n']}")
        for piece in body if isinstance(body, list) else [body]:
            yield ChatChunk(id="c", model="fake", delta_content=piece)
        yield ChatChunk(id="c", model="fake", finish_reason="stop", prompt_tokens=10, completion_tokens=100)
        yield ChatChunk(id="c", model="fake", wire_done=True)

    fake_provider.stream = stream  # type: ignore[method-assign]
    first = [e async for e in chat_service.chat(
        message="你好", conversation_id=None, stream=True, profile="immersive",
        auto_continue=False, max_tokens=256,
    )]
    cid = next(e for e in first if e.get("event") == "meta")["data"]["conversation_id"]
    events = [e async for e in chat_service.chat(
        message="你靠近一点", conversation_id=cid, stream=True, profile="immersive",
        auto_continue=True, max_tokens=6144,
    )]
    done = next(e for e in events if e.get("event") == "done")["data"]
    assert calls["n"] == 2
    assert copied not in done["message"]["content"]
