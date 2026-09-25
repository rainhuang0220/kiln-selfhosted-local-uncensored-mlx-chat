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
