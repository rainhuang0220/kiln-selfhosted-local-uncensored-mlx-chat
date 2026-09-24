from app.services.continuation import (
    TailStripper,
    continue_assistant_message,
    drop_last_token,
    shorten_until_unused,
    strip_regenerated_tail,
)


def test_shorten_until_unused_drops_further_on_retry():
    alphabet = "abcdefghij"
    encode = lambda text: [alphabet.index(ch) for ch in text]
    decode = lambda ids: "".join(alphabet[i] for i in ids)
    first, tail1 = shorten_until_unused(
        "abcdefghij",
        encode=encode,
        decode=decode,
        used=[],
    )
    assert first == "abcdefghi"
    assert tail1 == "j"
    second, tail2 = shorten_until_unused(
        "abcdefghij",
        encode=encode,
        decode=decode,
        used=[first],
    )
    assert second != first
    assert second == "abcdefgh"
    assert tail2 == "ij"


def test_continue_assistant_message_keeps_visible_and_reasoning():
    asst = continue_assistant_message("hello", "plan")
    assert asst == {"role": "assistant", "content": "hello", "reasoning_content": "plan"}
    assert "<think>" not in asst["content"]
    assert "<|im_start|>" not in asst["content"]


def test_drop_last_token_keeps_prefix():
    prompt, tail = drop_last_token(
        "abcde",
        encode=lambda text: list(range(len(text))),
        decode=lambda ids: "abcde"[: len(ids)] if ids != [4] else "e",
    )
    assert prompt == "abcd"
    assert tail == "e"


def test_strip_regenerated_tail_avoids_duplicate():
    assert strip_regenerated_tail("口还亮着", "口") == "还亮着"
    assert strip_regenerated_tail("边还亮着", "口") == "边还亮着"
    assert strip_regenerated_tail("还亮着", "") == "还亮着"


def test_tail_stripper_handles_chunked_deltas():
    stripper = TailStripper("口")
    assert stripper.feed("口") == ""
    assert stripper.feed("还亮着") == "还亮着"
    assert stripper.feed("。") == "。"


def test_tail_stripper_handles_split_tail():
    stripper = TailStripper("ing")
    assert stripper.feed("i") == ""
    assert stripper.feed("ng more") == " more"


def test_tail_stripper_returns_held_prefix_when_the_next_chunk_diverges():
    stripper = TailStripper("ing")
    assert stripper.feed("i") == ""
    assert stripper.feed("dea") == "idea"
    assert stripper.feed("s") == "s"
