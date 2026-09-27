from app.services.repetition import hard_self_loop, score_repetition

# Long enough to count as a full sentence under the sensory whitelist (≥40 chars).
_FULL = "他抬起头看向窗外，又把目光缓缓移回桌上那只空了的杯子，像是在等什么人先开口再说话。"


def test_hard_guard_requires_three_consecutive_sentences():
    text = f"{_FULL}{_FULL}{_FULL}"
    assert hard_self_loop(text) == _FULL
    almost = f"{_FULL}{_FULL}然后去倒了一杯水。"
    assert hard_self_loop(almost) is None


def test_hard_guard_ignores_common_particles_and_names():
    text = "她说她知道了。我觉得这样也好。我们继续走。"
    assert hard_self_loop(text) is None
    metrics = score_repetition(text)
    assert metrics.immediate_self_loop_count == 0


def test_offline_metrics_flag_duplicate_sentences():
    text = "门开了。灯还亮着。门开了。"
    report = score_repetition(text)
    assert report.sentence_count == 3
    assert report.duplicate_sentence_ratio > 0
    assert report.near_duplicate_sentence_count >= 1


def test_t_guard_sensory_short_clauses_not_hard_loop():
    """8–40 char sensory repeats (breath / contact deepening) must not abort the turn."""
    clause = "他的指腹又往下压深了一分。"  # 13 chars, full terminator
    assert 12 <= len(clause.replace("。", "")) <= 30
    text = clause * 3
    assert hard_self_loop(text) is None
    # Unterminated overlapping tail of the same length also stays soft.
    bare = "呼吸又乱了一拍贴着她的腰"
    assert 12 <= len(bare) <= 30
    assert hard_self_loop(bare * 3) is None


def test_t_guard_full_sentences_still_hard_loop():
    text = f"{_FULL}{_FULL}{_FULL}"
    assert hard_self_loop(text) == _FULL
