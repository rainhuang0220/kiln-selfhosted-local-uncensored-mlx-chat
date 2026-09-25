from app.services.answer_verify import minimal_evidence, verify_answer


def test_restores_unit_from_evidence_without_inventing_one():
    checked = verify_answer(
        question="缺页有多少卷",
        evidence="其中187卷缺页。",
        model_output="187",
    )
    assert checked.answer == "187卷"
    assert checked.model_number_ok is True
    assert checked.unit_restored is True
    assert checked.source == "evidence"


def test_rejects_a_wrong_difference_and_uses_the_last_two_measurements():
    evidence = "去年同日的处理水量是700吨。当日处理水量是640吨。外排达标水量是590吨。"
    checked = verify_answer(
        question="当日处理水量比外排达标水量多多少吨",
        evidence=evidence,
        model_output="60",
    )
    assert checked.answer == "50吨"
    assert checked.model_number_ok is False
    assert checked.source == "evidence_difference"


def test_newline_and_sludge_do_not_change_the_named_difference():
    evidence = "去年同日的处理水量是700吨。当日处理水量是640吨。外排达标水量是590吨。傍晚污泥外运是12吨。"
    checked = verify_answer(
        question="当日处理水量比外排达标水量多多少吨",
        evidence=evidence.replace("590", "59\n0"),
        model_output="60",
    )
    assert checked.answer == "50吨"
    assert checked.model_number_ok is False


def test_temperature_difference_ignores_the_earlier_process():
    evidence = "素烧温度是900摄氏度。目标保温是1280摄氏度。实际最高温度只到1265摄氏度。"
    checked = verify_answer(
        question="目标保温比实际最高温度高多少摄氏度",
        evidence=evidence,
        model_output="25",
    )
    assert checked.answer == "15摄氏度"
    assert checked.model_number_ok is False


def test_verbatim_quote_drops_the_extra_sentence():
    quote = "夜场只允许 ExhibitLight.dim 把东库三号柜降到40勒克斯。"
    checked = verify_answer(
        question="请逐字写出包含 ExhibitLight.dim 的那一句原文",
        evidence=quote,
        model_output="脚本里有一句不许改写。夜场只允许 ExhibitLight.dim 把东库三号柜降到 40 勒克斯。",
    )
    assert checked.answer == quote
    assert checked.extra_context is True
    assert checked.model_number_ok is True


def test_minimal_evidence_is_the_quote_not_the_surrounding_chunk():
    text = "前文无关。" * 30 + "当日处理水量是640吨。外排达标水量是590吨。" + "后文无关。" * 30
    start, end, span = minimal_evidence(text, "当日处理水量是640吨。外排达标水量是590吨。")
    assert text[start:end] == span
    assert len(span) < 80
    assert "前文无关" not in span
