"""Guards that keep one immersive turn above the visible-char floor without junk."""

from __future__ import annotations

from app.services.auto_continue import (
    count_output_chars,
    drop_last_sentence,
    fill_hop_tokens,
    runon_start,
    trim_to_sentence,
)
from app.services.continuation import EchoSuppressor
from app.services.repetition import repeated_sentence_start

PREV = "夕阳从木格窗斜斜挤进来，把尘埃染成暗金。她把铜钥匙推回柜台，指尖停在木纹上。“周五，公子可别忘了。”"


def _feed_all(sup: EchoSuppressor, text: str, step: int = 7) -> str:
    out = ""
    for i in range(0, len(text), step):
        out += sup.feed(text[i : i + step])
    return out + sup.flush()


def test_echo_suppressor_drops_verbatim_reprint_of_previous_reply():
    new = "门口的风铃响了一下，她没有抬头。"
    got = _feed_all(EchoSuppressor(PREV), PREV + "\n\n" + new)
    assert got.strip() == new


def test_echo_suppressor_keeps_diverging_sentence_whole():
    first_sentence = "夕阳从木格窗斜斜挤进来，把尘埃染成暗金。"
    diverged = "她没有碰那把铜钥匙，只把账本合上。"
    got = _feed_all(EchoSuppressor(PREV), first_sentence + diverged)
    assert got == diverged


def test_echo_suppressor_passes_fresh_text_unchanged():
    fresh = "夕阳落下去以后，店里只剩一盏灯。"
    assert _feed_all(EchoSuppressor(PREV), fresh) == fresh
    assert _feed_all(EchoSuppressor(""), fresh) == fresh


def test_runon_start_flags_long_unpunctuated_tail():
    salad = "探索发现感受体验领悟理解欣赏享受创造分享传递延续扩展延伸升华突破创新超越挑战" * 3
    text = "她笑了笑，把门关上。" + salad
    cut = runon_start(text, limit=80)
    assert cut == len("她笑了笑，把门关上。")
    assert runon_start("她笑了笑，把门关上。" + salad[:40], limit=80) is None


def test_repeated_sentence_start_finds_paragraph_cycle():
    a = "窗外的天色彻底暗了下来，只剩几盏昏黄的灯泡在尘埃里挣扎。"
    b = "我伸出左手，指尖轻轻掠过左耳后的那一块皮肤。"
    text = a + b + "\n\n“公子，”我低低唤道。\n\n" + a
    assert repeated_sentence_start(text) == len(text) - len(a)
    assert repeated_sentence_start(text[:-3]) is None
    assert repeated_sentence_start(a + b) is None
    refrain = "“周五当面还。”" + b + "“周五当面还。”"
    assert repeated_sentence_start(refrain) is None
    quoted = "“这把钥匙，若是真如你所言，便算缘分。”" + b + "“这把钥匙，若是真如你所言，便算缘分。”"
    assert repeated_sentence_start(quoted) == len(quoted) - len("“这把钥匙，若是真如你所言，便算缘分。”")
    after_quote = b + "“好。”" + b
    assert repeated_sentence_start(after_quote) == len(after_quote) - len(b)


def test_drop_last_sentence():
    assert drop_last_sentence("甲说完了。乙也说完了。\n\n") == "甲说完了。"
    assert drop_last_sentence("只有一句。") == "只有一句。"


def test_trim_to_sentence_respects_floor():
    text = "甲" * 5100 + "。她把钥匙收进袖口，然后"
    assert trim_to_sentence(text, min_chars=5000).endswith("。")
    short = "甲" * 100 + "。她把钥匙收进袖口，然后"
    assert trim_to_sentence(short, min_chars=5000) == short


def test_fill_hop_tokens_aims_past_floor_within_cap():
    tokens = fill_hop_tokens(
        visible_chars=2000, visible_tokens=1500, min_output_chars=5000, cap=6144
    )
    chars_per_token = 2000 / 1500
    assert (5000 - 2000) / chars_per_token < tokens <= 6144
    assert fill_hop_tokens(
        visible_chars=4990, visible_tokens=3000, min_output_chars=5000, cap=6144
    ) >= 256
    assert fill_hop_tokens(
        visible_chars=0, visible_tokens=0, min_output_chars=5000, cap=2000
    ) == 2000
    assert count_output_chars("一 二") == 2
