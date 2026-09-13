import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "benchmarks" / "generation-fidelity" / "prompts.json"
VISUAL = ROOT / "benchmarks" / "generation-fidelity" / "visual_ab.json"
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


def test_visual_ab_prompts_are_public_and_structured():
    data = json.loads(VISUAL.read_text(encoding="utf-8"))
    blob = json.dumps(data, ensure_ascii=False).lower()
    for marker in PRIVATE_MARKERS:
        assert marker not in blob
    assert len(data["image"]) >= 8
    axes = {c["axis"] for item in data["image"] for c in item["constraints"]}
    assert {"count", "spatial", "action", "attribute", "camera"} <= axes
    assert len(data["video"]) >= 2
    for item in data["image"] + data["video"]:
        assert item["prompt"].strip()
        assert item["constraints"]
        assert all("axis" in c and "text" in c for c in item["constraints"])


def test_summarize_scores_example_means():
    path = ROOT / "benchmarks" / "generation-fidelity" / "summarize_scores.py"
    spec = importlib.util.spec_from_file_location("summarize_scores", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    data = json.loads((ROOT / "benchmarks" / "generation-fidelity" / "example-scores.json").read_text(encoding="utf-8"))
    raw = [c for c in data["items"] if c["mode"] == "raw"]
    enh = [c for c in data["items"] if c["mode"] == "enhanced"]
    assert abs(mod.mean_adherence(raw) - 0.5) < 1e-9
    assert abs(mod.mean_adherence(enh) - 1.0) < 1e-9


def test_constraint_score_schema_exists():
    path = ROOT / "benchmarks" / "generation-fidelity" / "constraint-score.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert "PASS" in schema["properties"]["constraints"]["items"]["properties"]["verdict"]["enum"]


def test_visual_ab_runner_can_target_flux1_dev():
    text = (ROOT / "benchmarks" / "generation-fidelity" / "run_visual_ab.py").read_text(encoding="utf-8")
    assert "--backend" in text
    assert "flux1-dev" in text


def test_image_presets_quality_selects_flux1_dev():
    from app.services.image_presets import resolve

    params, backend = resolve({"preset": "quality", "seed": 42}, "z-image-turbo")
    assert backend == "flux1-dev"
    assert params["steps"] == 20
    assert params["guidance"] == 3.5
    fast, fast_backend = resolve({"preset": "fast"}, None)
    assert fast_backend == "z-image-turbo"
    assert fast["steps"] == 9


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
