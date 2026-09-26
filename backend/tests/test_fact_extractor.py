from app.services.fact_extractor import extract_facts, must_keep_fence


def test_extract_inventory_from_untagged_sentence():
    facts = extract_facts("钥匙还在你那儿吗？周五记得带过来。")
    assert "钥匙" in facts.inventory or "铜钥匙" in facts.inventory
    assert "周五" in facts.time_agreements


def test_extract_copper_key_without_location_label():
    facts = extract_facts("对了，铜钥匙。")
    assert "铜钥匙" in facts.inventory
    fence = must_keep_fence(facts.inventory)
    assert fence is not None
    assert "<must_keep>" in fence
    assert "铜钥匙" in fence


def test_extract_negative_preference():
    facts = extract_facts("不要叫我宝宝，好吗？")
    assert any("宝宝" in p for p in facts.preferences)


def test_extract_body_and_clothing():
    facts = extract_facts("他解开衬衫，靠过来吻她。")
    assert "解" in "".join(facts.body_actions) or "吻" in facts.body_actions
    assert "衬衫" in facts.clothing
