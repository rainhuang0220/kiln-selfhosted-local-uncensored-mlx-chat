from app.services.literary_system import IMMERSIVE_SYSTEM, compile_system


def test_immersive_system_forbids_ai_meta():
    assert "作为 AI" in IMMERSIVE_SYSTEM or "禁止「作为 AI」" in IMMERSIVE_SYSTEM
    assert "沉浸对话" in IMMERSIVE_SYSTEM
    # Reject legacy product labels (escaped so the wording gate can stay green).
    for token in ("\u6587\u7231", "\u8272\u60c5", "\u60c5\u8272"):
        assert token not in IMMERSIVE_SYSTEM
    assert "5000" in IMMERSIVE_SYSTEM
    assert "应用层不做内容过滤器" in IMMERSIVE_SYSTEM or "不说教" in IMMERSIVE_SYSTEM


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
    # contract forbids the model from speaking as AI; the ban phrase itself is ok
    assert "不是助手" in text
