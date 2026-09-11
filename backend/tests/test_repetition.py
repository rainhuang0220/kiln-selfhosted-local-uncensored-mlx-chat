from app.services.repetition import hard_self_loop, score_repetition


def test_hard_guard_requires_three_consecutive_sentences():
    text = "他抬起头看向窗外。他抬起头看向窗外。他抬起头看向窗外。"
    assert hard_self_loop(text) == "他抬起头看向窗外。"
    almost = "他抬起头看向窗外。他抬起头看向窗外。然后去倒了一杯水。"
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
