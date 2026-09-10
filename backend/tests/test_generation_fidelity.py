import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "benchmarks" / "generation-fidelity" / "prompts.json"
SCHEMA = ROOT / "benchmarks" / "generation-fidelity" / "schema.json"

PRIVATE_MARKERS = (
    "8-year",
    "8 year",
    "eight-year",
    "child sex",
    "csam",
)


def test_fidelity_prompts_are_public_and_benign():
    data = json.loads(PROMPTS.read_text(encoding="utf-8"))
    assert data["items"]
    blob = json.dumps(data, ensure_ascii=False).lower()
    for marker in PRIVATE_MARKERS:
        assert marker not in blob
    kinds = {item["kind"] for item in data["items"]}
    assert {"image", "video", "chat"} <= kinds


def test_fidelity_schema_has_required_axes():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    required = set(schema["properties"]["scores"]["required"])
    assert required == {
        "prompt_preservation",
        "subject",
        "attributes",
        "count",
        "spatial",
        "action",
        "style",
        "overall",
    }
