import pytest

from app.services.quality_metrics import (
    assistant_boundary_diversity,
    char_ngram_repeat_ratio,
    classify_followup,
    exact_duplicate_sentence_ratio,
    longest_repeated_substring,
    low_info_followup,
    near_duplicate_sentence_hits,
    normalize_cjk,
    paragraph_near_duplicate_ratio,
    repeated_ngram_ratio,
    summarize_run,
)


def test_normalize_cjk_collapses_space_and_case():
    assert normalize_cjk("  Hello，世界  ") == "hello,世界"
    assert normalize_cjk("青苔\n在微光里") == "青苔在微光里"


def test_exact_duplicate_sentence_ratio_counts_cjk_repeats():
    texts = [
        "瓦当上的青苔在微光里泛着墨色。",
        "残雪在檐角悄然消融。",
        "瓦当上的青苔在微光里泛着墨色。",
    ]
    assert exact_duplicate_sentence_ratio(texts) == pytest.approx(1 / 3)


def test_near_duplicate_flags_paraphrase_not_unrelated():
    prior = [
        "瓦当上的青苔在微光里泛着墨色，像是一枚枚静默的印章。",
        "残雪在檐角悄然消融，顺着瓦沟滴落。",
    ]
    hits = near_duplicate_sentence_hits(
        "青苔在微光里泛着墨色，像静默的印章。",
        prior,
        threshold=0.55,
    )
    assert hits >= 1
    assert (
        near_duplicate_sentence_hits("钥匙还在抽屉第二层。", prior, threshold=0.55)
        == 0
    )


def test_char_ngrams_work_without_english_spaces():
    text = "钥匙还在抽屉钥匙还在抽屉"
    assert repeated_ngram_ratio(text, 4) > 0.3
    assert char_ngram_repeat_ratio(text, 3) > 0
    assert "钥匙还在抽屉" in longest_repeated_substring(text, min_len=4)


def test_opening_closing_diversity_and_low_info_followup():
    openings = ["风把那盏灯", "那光在潮湿", "风把那盏灯", "夜色更深了"]
    closings = ["推门进来。", "推门进来。", "守候着归途。", "未写完的诗。"]
    div = assistant_boundary_diversity(openings, closings)
    assert div["opening"] < 1
    assert 0 < div["closing"] <= 1
    assert low_info_followup("嗯") == "low_info"
    assert low_info_followup("嗯。") == "low_info"
    assert low_info_followup("然后呢？") == "low_info"
    assert low_info_followup("……") == "low_info"
    assert low_info_followup("钥匙还在你那儿吗？") == "substantive"
    assert (
        classify_followup("雨停了，我去关窗。", user_was_low_info=True, previous=[])
        == "new_event"
    )
    assert (
        classify_followup("然后呢？现在呢？", user_was_low_info=True, previous=[])
        == "question_only"
    )


def test_summarize_run_includes_required_keys():
    summary = summarize_run(
        [
            {
                "content": "瓦当上的青苔在微光里泛着墨色。",
                "finish_reason": "stop",
                "ttft_s": 0.7,
                "decode_tok_s": 20.0,
                "cached_tokens": 80,
                "prompt_tokens": 100,
                "completion_tokens": 30,
                "protocol_failure": False,
                "repetition_guard": False,
                "low_info_user": True,
                "followup_class": "new_event",
            },
            {
                "content": "瓦当上的青苔在微光里泛着墨色。",
                "finish_reason": "length",
                "ttft_s": 7.0,
                "decode_tok_s": 19.0,
                "cached_tokens": 0,
                "prompt_tokens": 200,
                "completion_tokens": 40,
                "protocol_failure": True,
                "repetition_guard": True,
                "low_info_user": True,
                "followup_class": "question_only",
            },
        ]
    )
    for key in (
        "exact_duplicate_sentence_ratio",
        "normalized_duplicate_sentence_ratio",
        "repeated_3gram",
        "repeated_4gram",
        "repeated_5gram",
        "longest_repeated_substring",
        "paragraph_near_duplicate_ratio",
        "opening_diversity",
        "closing_diversity",
        "avg_response_tokens",
        "p50_response_tokens",
        "p95_response_tokens",
        "length_finish_count",
        "stop_finish_count",
        "protocol_failure_count",
        "repetition_guard_count",
        "ttft_p50",
        "ttft_p95",
        "decode_tok_s_p50",
        "cache_hit_p50",
        "prompt_tokens",
        "low_info_question_only",
        "low_info_new_event",
    ):
        assert key in summary
    assert summary["length_finish_count"] == 1
    assert summary["protocol_failure_count"] == 1
    assert paragraph_near_duplicate_ratio(
        ["青苔在微光里。", "青苔在微光里。"]
    ) > 0
