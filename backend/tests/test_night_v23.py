"""Night V23: paragraph-cycle loop guard and immersive repetition floor."""

from __future__ import annotations

from pathlib import Path

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


def test_default_hop_carries_nameless_style_digest():
    from app.services.context_compiler import route_context

    for message in ("你好", "你靠近一点"):
        fence = route_context(_parlor_ir(), message).fence
        assert "技师" in fence and "接待室" in fence
        assert fence.index("<active_context>") < fence.index("<style_digest")
        digest = fence.split("<style_digest", 1)[1].split("</style_digest>", 1)[0]
        assert 'do_not_literalize="true"' in digest
        assert len(digest) >= 160
        assert "客人" in digest and "呼吸" in digest
        assert "以下内容" not in digest
        assert len(fence) <= 900
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


def test_grounded_contract_allows_present_beat_senses_and_forbids_menus():
    from app.services.literary_system import GROUNDED_CONTEXT_SYSTEM

    assert "衣着变化属于这一拍" in GROUNDED_CONTEXT_SYSTEM
    assert "未给出的光线、气味、衣着" not in GROUNDED_CONTEXT_SYSTEM
    assert "不要列选项" in GROUNDED_CONTEXT_SYSTEM
    assert "请用户选择先看哪里" not in GROUNDED_CONTEXT_SYSTEM
