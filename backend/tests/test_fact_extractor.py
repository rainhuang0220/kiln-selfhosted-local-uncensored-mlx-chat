from app.services.fact_extractor import (
    extract_atoms,
    extract_facts,
    must_keep_fence,
    pins_absent_from_prose,
    pack_user_side_fences,
)


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


def test_extract_body_marks_and_locations_substring():
    facts = extract_facts("旧书店柜台旁，左耳后有颗红痣。")
    assert "红痣" in facts.body_marks or "左耳后红痣" in facts.body_marks
    assert "左耳后" in "".join(facts.body_marks)
    assert "旧书店" in facts.locations
    assert "柜台" in facts.locations


def test_extract_atoms_structured_pins_from_untagged_text():
    atoms = extract_atoms(
        "旧书店里，铜钥匙在柜台。周五当面还。只叫公子。左耳后红痣。",
        prev_assistant="",
    )
    blob = "\n".join(atoms)
    assert 1 <= len(atoms) <= 12
    assert "称呼：公子" in blob
    assert "物件：铜钥匙" in blob or "物件：铜钥匙在柜台" in blob
    assert "约定：周五" in blob
    assert "地点：旧书店" in blob
    assert "标记：" in blob and ("红痣" in blob or "左耳后" in blob)


def test_extract_atoms_prefer_labeled_lines():
    atoms = extract_atoms("称呼：公子\n标记：左耳后红痣\n物件：铜钥匙\n约定：周五\n地点：旧书店")
    assert "称呼：公子" in atoms
    assert "标记：左耳后红痣" in atoms
    assert "物件：铜钥匙" in atoms
    assert "约定：周五" in atoms
    assert "地点：旧书店" in atoms


def test_extract_atoms_labeled_values_stop_at_sentence_end():
    atoms = extract_atoms("地点：旧书店。物件：铜钥匙。约定：周五。称呼：公子。标记：红痣。")
    for pin in ("地点：旧书店", "物件：铜钥匙", "约定：周五", "称呼：公子", "标记：红痣"):
        assert pin in atoms, (pin, atoms)
    assert not [a for a in atoms if "。" in a], atoms


def test_extract_atoms_are_short_and_not_redundant():
    atoms = extract_atoms(
        "我把铜钥匙放在柜台上，周五当面还你。你左耳后有一颗红痣。",
        prev_assistant="夕阳从旧书店的窗户照进来。那枚红痣在左耳后。她把灯拧亮。",
    )
    assert "标记：左耳后红痣" in atoms
    assert "标记：红痣" not in atoms
    assert "标记：左耳后" not in atoms
    assert "物件：铜钥匙在柜台" in atoms
    assert "地点：柜台" not in atoms
    assert "物件：窗" not in atoms
    assert "物件：灯" not in atoms


def test_extract_atoms_includes_previous_assistant():
    atoms = extract_atoms("嗯。", prev_assistant="他把铜钥匙放回旧书店柜台。")
    blob = "\n".join(atoms)
    assert "铜钥匙" in blob
    assert "旧书店" in blob or "柜台" in blob


def test_must_keep_uses_structured_atoms():
    atoms = extract_atoms("公子拿着铜钥匙，周五来旧书店。红痣还在。")
    fence = must_keep_fence(atoms)
    assert fence is not None
    assert fence.startswith("<must_keep>")
    assert "称呼：公子" in fence or "公子" in fence
    assert "铜钥匙" in fence
    assert "周五" in fence


def test_pins_absent_allows_key_synonym():
    pins = ["物件：铜钥匙", "约定：周五", "称呼：公子"]
    assert pins_absent_from_prose(pins, "他把钥匙递过来，说周五见，公子。") == []
    missing = pins_absent_from_prose(pins, "他笑了笑，什么也没提。")
    assert any("铜钥匙" in m or "物件" in m for m in missing)
    assert any("周五" in m for m in missing)


def test_pack_user_side_fences_order_and_lore_truncate():
    keep = must_keep_fence(["称呼：公子", "物件：铜钥匙"])
    lore = "<lore>\n" + ("旧书店设定。" * 80) + "\n</lore>"
    scene = "<scene_state>\nlocation: 旧书店\ninventory: [铜钥匙]\nclock: 周五约定\n</scene_state>"
    packed = pack_user_side_fences(
        must_keep=keep,
        lore=lore,
        scene_state=scene,
        budget_chars=400,
    )
    assert packed is not None
    assert packed.index("<must_keep>") < packed.index("<lore>")
    assert packed.index("<lore>") < packed.index("<scene_state>")
    assert len(packed) <= 420
    assert "铜钥匙" in packed
