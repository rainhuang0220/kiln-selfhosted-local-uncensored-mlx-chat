import hashlib

from app.services.context_route import cache_identity, describe_input, route_document


def test_archive_roundtrip_keeps_twenty_thousand_characters():
    text = "测" * 20000
    routed = route_document(
        text=text,
        question="请逐字输出全文",
        token_budget=20000,
        reserved_output=1024,
        count_tokens=lambda s: len(s),
    )
    assert routed.original_chars == 20000
    assert routed.archive.text == text
    assert routed.archive.sha256
    assert routed.silent_truncation is False
    assert routed.mode == "verbatim_exceeds_budget"
    assert routed.model_text is None
    assert routed.represents_full_document is False


def test_verbatim_under_budget_sends_every_character():
    text = "甲" * 100 + "乙"
    routed = route_document(
        text=text,
        question="总结一下",
        token_budget=500,
        reserved_output=32,
        count_tokens=lambda s: len(s),
    )
    assert routed.mode == "verbatim"
    assert routed.model_text == text
    assert routed.represents_full_document is True
    assert routed.original_chars == routed.served_chars == len(text)


def test_character_count_and_token_count_stay_separate():
    text = "测" * 20000
    counted = describe_input(text, count_tokens=lambda s: len(s) // 2)
    assert counted["chars"] == 20000
    assert counted["tokens"] == 10000
    assert counted["chars"] != counted["tokens"]


def test_retrieval_marks_a_subset_and_keeps_the_original():
    head = "前言。" * 400
    fact = "证据编号 KILN-8841。"
    tail = "后记。" * 400
    text = head + fact + tail
    routed = route_document(
        text=text,
        question="证据编号是什么",
        token_budget=80,
        reserved_output=16,
        count_tokens=lambda s: len(s),
        chunk_chars=40,
    )
    assert routed.mode == "retrieval"
    assert routed.represents_full_document is False
    assert routed.archive.text == text
    assert routed.original_chars == len(text)
    assert routed.served_chars < routed.original_chars
    assert routed.model_text is not None
    assert "KILN-8841" in routed.model_text
    assert routed.silent_truncation is False
    for cite in routed.citations:
        assert text[cite.start : cite.end] == cite.text
        assert cite.chunk_id.startswith(routed.archive.doc_id)


def test_chunk_ids_do_not_change_between_calls():
    text = "段" * 500
    first = route_document(
        text=text,
        question="这段在说什么",
        token_budget=40,
        reserved_output=8,
        count_tokens=lambda s: len(s),
        chunk_chars=50,
    )
    second = route_document(
        text=text,
        question="这段在说什么",
        token_budget=40,
        reserved_output=8,
        count_tokens=lambda s: len(s),
        chunk_chars=50,
    )
    assert [c.chunk_id for c in first.citations] == [c.chunk_id for c in second.citations]
    assert first.archive.sha256 == second.archive.sha256


def test_cache_identity_changes_when_template_or_thinking_changes():
    base = cache_identity(model="9b", revision="rev-a", template="tmpl", thinking=False)
    assert base == cache_identity(model="9b", revision="rev-a", template="tmpl", thinking=False)
    assert base != cache_identity(model="9b", revision="rev-b", template="tmpl", thinking=False)
    assert base != cache_identity(model="9b", revision="rev-a", template="other", thinking=False)
    assert base != cache_identity(model="9b", revision="rev-a", template="tmpl", thinking=True)


def _long_fact_document() -> str:
    fact = "证据编号 KILN-8841 以及 SECOND-FACT。"
    return ("前言。" * 400) + fact + ("后记。" * 400)


def test_compression_preserves_archive_hash_and_shortens_model_text():
    fact_a = "ALPHA-7"
    fact_b = "BETA-9"
    text = ("甲" * 300) + f"保留 {fact_a} 与 {fact_b}。" + ("乙" * 300)
    seen: list[str] = []

    def compressor(src: str) -> str:
        seen.append(src)
        return f"压缩 {fact_a} {fact_b}"

    routed = route_document(
        text=text,
        question="概括要点",
        token_budget=80,
        reserved_output=8,
        count_tokens=lambda s: len(s),
        compressor=compressor,
        required_facts=(fact_a, fact_b),
    )
    baseline = route_document(
        text=text,
        question="概括要点",
        token_budget=80,
        reserved_output=8,
        count_tokens=lambda s: len(s),
    )
    assert seen == [text]
    assert routed.mode == "compression"
    assert routed.model_text == f"压缩 {fact_a} {fact_b}"
    assert routed.model_text is not None
    assert len(routed.model_text) < len(text)
    assert routed.served_chars == len(routed.model_text)
    assert routed.original_chars == len(text)
    assert routed.represents_full_document is False
    assert routed.silent_truncation is False
    assert routed.fallback_reason is None
    assert routed.citations == []
    assert routed.archive.text == text
    assert routed.archive.sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert routed.archive.sha256 == baseline.archive.sha256
    assert routed.archive.text == baseline.archive.text
    assert routed.original_tokens == len(text)
    assert routed.served_tokens == len(routed.model_text)
    assert routed.served_tokens <= 80 - 8


def test_compression_accepts_exact_budget():
    text = "甲" * 200 + "FACT-1"
    payload = "FACT-1" + ("乙" * 24)

    def compressor(_: str) -> str:
        return payload

    routed = route_document(
        text=text,
        question="概括",
        token_budget=40,
        reserved_output=10,
        count_tokens=lambda s: len(s),
        compressor=compressor,
        required_facts=("FACT-1",),
    )
    assert len(payload) == 30
    assert routed.mode == "compression"
    assert routed.model_text == payload
    assert routed.served_tokens == 30
    assert routed.original_tokens == len(text)
    assert routed.archive.text == text
    assert routed.represents_full_document is False


def test_compressor_exception_falls_back_to_retrieval():
    text = _long_fact_document()
    calls = {"n": 0}

    def compressor(_: str) -> str:
        calls["n"] += 1
        raise RuntimeError("compress failed")

    routed = route_document(
        text=text,
        question="证据编号是什么",
        token_budget=80,
        reserved_output=16,
        count_tokens=lambda s: len(s),
        chunk_chars=40,
        compressor=compressor,
        required_facts=("KILN-8841", "SECOND-FACT"),
    )
    assert calls["n"] == 1
    assert routed.mode == "retrieval"
    assert routed.fallback_reason == "compressor_error"
    assert routed.archive.text == text
    assert routed.archive.sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert routed.model_text is not None
    assert "KILN-8841" in routed.model_text
    assert "compress failed" not in routed.model_text
    for cite in routed.citations:
        assert text[cite.start : cite.end] == cite.text
        assert cite.chunk_id.startswith(routed.archive.doc_id)


def test_missing_required_fact_falls_back_to_original_citations():
    text = _long_fact_document()

    def compressor(_: str) -> str:
        return "只留下 KILN-8841"

    routed = route_document(
        text=text,
        question="证据编号是什么",
        token_budget=80,
        reserved_output=16,
        count_tokens=lambda s: len(s),
        chunk_chars=40,
        compressor=compressor,
        required_facts=("KILN-8841", "SECOND-FACT"),
    )
    assert routed.mode == "retrieval"
    assert routed.fallback_reason == "missing_required_facts"
    assert routed.archive.text == text
    assert routed.model_text is not None
    assert routed.model_text != "只留下 KILN-8841"
    assert "SECOND-FACT" in routed.model_text
    found = False
    for cite in routed.citations:
        assert text[cite.start : cite.end] == cite.text
        assert cite.chunk_id.startswith(routed.archive.doc_id)
        if "SECOND-FACT" in cite.text:
            found = True
    assert found


def test_empty_unchanged_and_over_budget_compressions_fall_back():
    text = _long_fact_document()
    room = 80 - 16
    sentinel = "COMPRESSED-BUT-TOO-LONG-" + ("Z" * (room + 5))

    def empty(_: str) -> str:
        return ""

    def same(src: str) -> str:
        return src

    def too_long(_: str) -> str:
        return sentinel + "KILN-8841 SECOND-FACT"

    cases = (
        (empty, "empty"),
        (same, "unchanged"),
        (too_long, "over_budget"),
    )
    for compressor, reason in cases:
        routed = route_document(
            text=text,
            question="证据编号是什么",
            token_budget=80,
            reserved_output=16,
            count_tokens=lambda s: len(s),
            chunk_chars=40,
            compressor=compressor,
            required_facts=("KILN-8841", "SECOND-FACT"),
        )
        assert routed.mode == "retrieval"
        assert routed.fallback_reason == reason
        assert routed.archive.text == text
        assert routed.archive.sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert routed.model_text is not None
        assert routed.model_text != text
        assert sentinel not in routed.model_text
        assert "SECOND-FACT" in routed.model_text
        for cite in routed.citations:
            assert text[cite.start : cite.end] == cite.text


def test_verbatim_question_does_not_call_compressor():
    text = "测" * 5000
    seen: list[str] = []

    def compressor(src: str) -> str:
        seen.append(src)
        return "x"

    for mark in ("逐字", "原文", "全文", "精确", "代码", "引用位置"):
        seen.clear()
        routed = route_document(
            text=text,
            question=f"请按{mark}回答",
            token_budget=100,
            reserved_output=10,
            count_tokens=lambda s: len(s),
            compressor=compressor,
            required_facts=("测",),
        )
        assert seen == []
        assert routed.mode == "verbatim_exceeds_budget"
        assert routed.model_text is None
        assert routed.archive.text == text
        assert routed.represents_full_document is False


def test_text_that_fits_does_not_call_compressor_even_for_verbatim_question():
    seen: list[str] = []

    def compressor(src: str) -> str:
        seen.append(src)
        return "x"

    text = "短文"
    routed = route_document(
        text=text,
        question="请逐字输出",
        token_budget=50,
        reserved_output=5,
        count_tokens=lambda s: len(s),
        compressor=compressor,
        required_facts=("不存在的事实",),
    )
    assert seen == []
    assert routed.mode == "verbatim"
    assert routed.model_text == text
    assert routed.represents_full_document is True
    assert routed.archive.sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
