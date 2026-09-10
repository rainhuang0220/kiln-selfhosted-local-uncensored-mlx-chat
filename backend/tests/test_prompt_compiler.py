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
