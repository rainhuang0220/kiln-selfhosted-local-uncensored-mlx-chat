from app.services.literary_system import IMMERSIVE_SYSTEM, compile_system


def test_immersive_system_keeps_only_the_short_scene_contract():
    assert "写成人向文爱小说" in IMMERSIVE_SYSTEM
    assert "先接上一句用户输入" in IMMERSIVE_SYSTEM
    assert "此刻现场" in IMMERSIVE_SYSTEM
    for token in ("角色演员", "至少 1500", "5000", "10000 字", "接触面、呼吸、力道"):
        assert token not in IMMERSIVE_SYSTEM


def test_compile_system_includes_immutable_and_no_ai_assistant_voice():
    text = compile_system(
        {
            "name": "阿笙",
            "personality": "冷淡",
            "speech_style": "只叫用户「公子」",
            "taboos": "不提前任",
            "relationship_to_user": "主仆",
            "immutable_json": ["左耳一颗红痣", "只叫用户「公子」"],
            "scenario": "雨夜茶馆",
        }
    )
    assert "左耳一颗红痣" in text
    assert "公子" in text
    assert "<character>" in text
    assert "作为 AI" not in text.split("<character>")[0] or "禁止" in text
    assert text.startswith(IMMERSIVE_SYSTEM)
