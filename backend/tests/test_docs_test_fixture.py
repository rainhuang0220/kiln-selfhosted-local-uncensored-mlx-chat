"""The human-readable dense reference in docs/test is an executable regression case."""

import json
import re
from pathlib import Path


DOCS_TEST = Path(__file__).resolve().parents[2] / "docs" / "test"
SOURCE = (DOCS_TEST / "多人物交织场景_输入.md").read_text("utf-8")
GOLD = json.loads((DOCS_TEST / "多人物交织场景_标准结构.json").read_text("utf-8"))


def test_dense_reference_has_matching_gold_and_adult_cast():
    assert len(re.findall(r"[\u4e00-\u9fff]", SOURCE)) >= 2000
    assert len(GOLD["people"]) >= 10
    assert all(person["age"] >= 18 for person in GOLD["people"])
    assert all(person["name"] in SOURCE for person in GOLD["people"])
    evidence = [GOLD[key]["evidence"] for key in ("assistant_persona", "user_avatar", "current_scene")]
    evidence += [segment["evidence"] for segment in GOLD["segments"]]
    assert all(span in SOURCE for span in evidence)


def test_dense_reference_scopes_live_scene_and_harvests_cast():
    from app.services.context_presets import preview_preset, public_studio_payload
    from app.services.style_bank import split_style_corpus

    split = split_style_corpus(SOURCE)
    assert len(split.corpus) > 1800
    assert "陆遥" in split.corpus
    assert "陆遥" not in split.live

    draft = preview_preset(SOURCE)
    public = public_studio_payload(draft)
    names = {person["name"] for person in public["characters"]}
    expected = {person["name"] for person in GOLD["people"] if person["name"] != GOLD["narrator"]}
    assert expected == names
    assert GOLD["narrator"] in draft["me"]["identity"]
    assert "接待室" in draft["current_scene"]
    assert "多人物交织场景" not in draft["current_scene"]
    assert "陆遥" not in draft["current_scene"]
    assert "接待室" in draft["context_ir"]["current_scene"]
