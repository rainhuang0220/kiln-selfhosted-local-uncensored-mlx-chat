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
