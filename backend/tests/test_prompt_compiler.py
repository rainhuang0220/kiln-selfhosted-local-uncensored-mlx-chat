import pytest

from app.services.prompt_compiler import (
    IMAGE_SYSTEM,
    VIDEO_SYSTEM,
    compile_visual_prompt,
    mlx_compiler_payload,
    preservation_violations,
)


def test_local_compiler_targets_loaded_default_model():
    payload = mlx_compiler_payload("sys", "user")
    assert payload["model"] == "default_model"
    assert payload["chat_template_kwargs"]["enable_thinking"] is False
    assert payload["stream"] is False


def test_raw_mode_is_verbatim():
    got = compile_visual_prompt("red cube left of blue sphere", "image", mode="raw")
    assert got.effective == "red cube left of blue sphere"
    assert got.original == got.effective
    assert got.violations == []


def test_system_prompts_are_compilers_not_writers():
    for text in (IMAGE_SYSTEM, VIDEO_SYSTEM):
        assert "prompt compiler" in text.lower()
        assert "do not remove" in text.lower()
        assert "do not invent" in text.lower()


@pytest.mark.parametrize(
    "original,mutated,code",
    [
        ("a red cube", "a blue cube", "swapped:red->blue"),
        ("exactly three objects", "exactly four objects", "swapped:three->four"),
        ("cat left of dog", "cat right of dog", "swapped:left->right"),
        ("person standing", "person sitting", "swapped:standing->sitting"),
        ("night street", "daytime street", "swapped:night->daytime"),
        ("a red cube", "a cube on a table", "dropped:red"),
    ],
)
def test_preservation_detects_intent_edits(original, mutated, code):
    assert code in preservation_violations(original, mutated)


def test_enhanced_keeps_constraints_when_model_expands():
    def complete(system, user):
        assert "red cube" in user
        return (
            "SUBJECT: red cube left of blue sphere. ACTION: none. "
            "COMPOSITION: exactly three objects on a white ground. "
            "CAMERA: low angle. LIGHTING: even studio. STYLE: product photo. "
            "CONSTRAINTS: no text. "
            "Final: a red cube to the left of a blue sphere, exactly three objects, "
            "camera low angle, white background, no text."
        )

    got = compile_visual_prompt(
        "red cube left of blue sphere, exactly three objects, camera low angle, background white, no text",
        "image",
        mode="enhanced",
        complete_fn=complete,
    )
    assert got.violations == []
    assert "red" in got.effective.lower()
    assert "blue" in got.effective.lower()
    assert "three" in got.effective.lower()
    assert "left" in got.effective.lower()


def test_enhanced_falls_back_to_original_if_model_rewrites():
    def complete(system, user):
        return "a blue cube right of a red sphere in daylight, four objects"

    original = "red cube left of blue sphere, exactly three objects, night, person standing"
    got = compile_visual_prompt(original, "image", mode="enhanced", complete_fn=complete)
    assert got.effective == original
    assert got.violations


def test_enhanced_falls_back_when_chinese_constraints_lost():
    def complete(system, user):
        return "a blue car to the right of a red car in daylight, four people sitting"

    original = "画面里必须恰好有三个人。红色汽车在蓝色汽车左侧。人物站着，不要坐下。场景发生在夜晚。"
    got = compile_visual_prompt(original, "image", mode="enhanced", complete_fn=complete)
    assert got.effective == original
    assert got.violations


def test_enhanced_keeps_chinese_when_english_preserves_facts():
    def complete(system, user):
        return (
            "SUBJECT: exactly three people; a red car to the left of a blue car. "
            "ACTION: the people are standing, not sitting. "
            "ENVIRONMENT: nighttime. CONSTRAINTS: keep count three, left-of, standing, night."
        )

    original = "画面里必须恰好有三个人。红色汽车在蓝色汽车左侧。人物站着，不要坐下。场景发生在夜晚。"
    got = compile_visual_prompt(original, "image", mode="enhanced", complete_fn=complete)
    assert got.effective != original
    assert got.violations == []
    assert "three" in got.effective.lower()
    assert "left" in got.effective.lower()
    assert "standing" in got.effective.lower()
    assert "night" in got.effective.lower()


def test_translate_keeps_chinese_atomic_constraints():
    from app.services.prompt_compiler import translate_visual_prompt

    original = "画面里必须恰好有三个人。红色汽车在蓝色汽车左侧。人物站着，不要坐下。场景发生在夜晚。"

    def complete(system, user):
        assert "translat" in system.lower()
        return (
            "There must be exactly three people. A red car is to the left of a blue car. "
            "The people are standing, not sitting. The scene is at night."
        )

    got = translate_visual_prompt(original, complete_fn=complete)
    assert got.violations == []
    assert "three" in got.effective.lower()
    assert "left" in got.effective.lower()
    assert "standing" in got.effective.lower()
    assert "night" in got.effective.lower()


def test_translate_falls_back_when_facts_are_lost():
    from app.services.prompt_compiler import translate_visual_prompt

    original = "画面里必须恰好有三个人。红色汽车在蓝色汽车左侧。"

    def complete(system, user):
        return "several cars and some people during the day"

    got = translate_visual_prompt(original, complete_fn=complete)
    assert got.effective == original
    assert got.violations


def test_translate_enhance_runs_translate_then_enhance():
    original = "画面里必须恰好有三个人。红色汽车在蓝色汽车左侧。人物站着。夜晚。"
    systems: list[str] = []

    def complete(system, user):
        systems.append(system)
        if "translat" in system.lower():
            return (
                "exactly three people; a red car to the left of a blue car; "
                "the people are standing; the scene is at night"
            )
        return (
            "SUBJECT: exactly three people and a red car to the left of a blue car. "
            "ACTION: standing. ENVIRONMENT: night. CONSTRAINTS: keep count three, left-of, standing, night."
        )

    got = compile_visual_prompt(original, "image", mode="translate_enhance", complete_fn=complete)
    assert any("translat" in s.lower() for s in systems)
    assert any("prompt compiler" in s.lower() for s in systems)
    assert got.mode == "translate_enhance"
    assert got.effective != original
    assert "three" in got.effective.lower()
    assert "left" in got.effective.lower()


def test_video_prompt_asks_for_time_and_camera():
    captured = {}

    def complete(system, user):
        captured["system"] = system
        return (
            "subject copper kiln, appearance oxidized metal, initial state steaming, "
            "action over time slow camera push-in, camera movement dolly in, "
            "environment workshop, lighting cinematic, temporal consistency stable subject"
        )

    compile_visual_prompt(
        "a copper kiln steaming in a workshop, slow camera push-in",
        "video",
        mode="enhanced",
        complete_fn=complete,
    )
    sys = captured["system"].lower()
    assert "action over time" in sys
    assert "camera movement" in sys
    assert "do not pile empty quality words" in sys
