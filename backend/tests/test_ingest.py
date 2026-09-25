from app.services.ingest import pack_document, pack_user_message, requests_full_document, split_chunks, split_query_and_body


def test_cross_document_comparison_requires_full_source():
    assert requests_full_document("请比较两份文档的所有差异。\n# File: a.txt\n内容")
    assert requests_full_document("请对比这两段代码。\n# File: a.py\ncode")
    assert not requests_full_document("请找出发票编号。\n# File: a.txt\n内容")


def test_pack_keeps_named_section_evidence_in_long_compendium():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "engineering/mission-20260925/eval"
    document = (root / "semantic-compendium-2.txt").read_text()
    question = "在章节 [L43] 中，调度把夜班人数改成了多少人？"
    packed = pack_user_message(
        question + "\n# File: semantic-compendium-2.txt\n" + document,
        budget=10_000,
        estimate=len,
    )
    assert packed.applied
    assert "不是11人，请假后是8人。" in packed.text


def _est(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def test_split_query_and_body_keeps_prompt():
    q, b = split_query_and_body("summarize this\n# File: a.txt\nhello")
    assert q == "summarize this"
    assert b.startswith("# File: a.txt")


def test_split_chunks_covers_all_text():
    text = "\n\n".join(f"para {i} " + ("x" * 200) for i in range(12))
    chunks = split_chunks(text, chunk_chars=400, overlap_chars=20)
    assert len(chunks) >= 3
    assert "para 0" in chunks[0]
    assert "para 11" in chunks[-1]


def test_pack_noop_when_under_budget():
    text = "short file"
    packed = pack_document(text, budget=100, estimate=_est)
    assert packed.applied is False
    assert packed.text == text


def test_pack_keeps_head_and_tail():
    text = "HEADSTART " + ("middle-unique-aaa " * 400) + " TAILEND"
    packed = pack_document(text, budget=80, estimate=_est, query="TAILEND")
    assert packed.applied is True
    assert "HEADSTART" in packed.text
    assert "TAILEND" in packed.text
    assert packed.original_tokens > packed.kept_tokens
    assert "<document packed=\"true\"" in packed.text


def test_pack_user_message_preserves_question():
    content = "只回答文件里出现几次 foo。\n# File: n.txt\n" + ("foo bar " * 2000)
    packed = pack_user_message(content, budget=120, estimate=_est)
    assert packed.applied is True
    assert packed.text.startswith("只回答文件里出现几次 foo。")
    assert "<document packed=\"true\"" in packed.text
