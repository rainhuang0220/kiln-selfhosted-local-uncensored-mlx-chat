from app.services.constraint_verifier import (
    constraints_against_text,
    extract_constraints,
    extract_constraints_model,
    structured_violations,
)


def test_extracts_chinese_count_left_standing_night():
    text = (
        "画面里必须恰好有三个人。"
        "红色汽车在蓝色汽车左侧。"
        "人物站着，不要坐下。"
        "场景发生在夜晚。"
    )
    got = extract_constraints(text)
    types = {(c["type"], str(c["value"])) for c in got}
    assert ("count", "3") in types
    assert ("color", "red") in types
    assert ("color", "blue") in types
    assert ("relation", "left_of") in types
    assert ("pose", "standing") in types
    assert ("pose", "sitting") not in types
    assert ("time", "night") in types


def test_compiled_english_keeps_chinese_constraints():
    original = "画面里必须恰好有三个人。红色汽车在蓝色汽车左侧。人物站着，不要坐下。场景发生在夜晚。"
    effective = (
        "exactly three people; a red car to the left of a blue car; "
        "the person is standing, not sitting; the scene is at night"
    )
    report = constraints_against_text(extract_constraints(original), effective)
    assert all(item["status"] == "pass" for item in report)


def test_detects_chinese_constraint_swaps_in_compiled_text():
    original = "红色汽车在蓝色汽车左侧。恰好三个人。人物站着。夜晚。室内。俯视。"
    effective = "a blue car to the right of a red car, four people sitting in daytime outdoors, low-angle view"
    lost = structured_violations(original, effective)
    assert lost
    joined = " ".join(lost)
    assert "count" in joined or "3" in joined
    assert "left" in joined or "relation" in joined
    assert "standing" in joined or "pose" in joined
    assert "night" in joined or "time" in joined


def test_overhead_accepts_directly_above_english():
    original = "从正上方俯视一张圆形木桌。"
    assert not structured_violations(original, "a round wooden table viewed from directly above")


def test_extracts_bilingual_pair_lexicon():
    text = "四个蓝色物体在右边坐着，白天室外，背面仰视。"
    got = {(c["type"], str(c["value"])) for c in extract_constraints(text)}
    assert ("count", "4") in got
    assert ("color", "blue") in got
    assert ("relation", "right_of") in got
    assert ("pose", "sitting") in got
    assert ("time", "day") in got
    assert ("place", "outdoor") in got
    assert ("view", "back") in got
    assert ("camera", "low_angle") in got


def test_model_extract_falls_back_and_parses_json():
    def complete(system, user):
        assert "fidelity" in system.lower() or "constraints" in system.lower()
        return '{"constraints":[{"type":"count","value":"3"},{"type":"relation","subject":"red car","relation":"left_of","object":"blue car","value":"left_of"}]}'

    got = extract_constraints_model("红色汽车在蓝色汽车左侧。恰好三个人。", complete)
    types = {c["type"] for c in got}
    assert "count" in types
    assert "relation" in types
