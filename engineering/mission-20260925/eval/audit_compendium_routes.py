"""Audit evidence retention in the current Kiln document packer without MLX calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from backend.app.services.ingest import pack_user_message, requests_full_document  # noqa: E402
from backend.app.services.tokens import TokenEstimator  # noqa: E402


def audit() -> None:
    items = [json.loads(line) for line in (HERE / "compendium-20k-50.jsonl").read_text().splitlines()]
    tokenizer = TokenEstimator(str(REPO.parent / "qwen3.5-9b-hauhau-aggressive-mxfp4"))
    records = []
    for item in items:
        text = (HERE / item["corpus_file"]).read_text()
        message = f"{item['question']}\n# File: {item['corpus_file']}\n{text}"
        full = requests_full_document(message)
        budget = 32_768 if full else 10_240
        packed = pack_user_message(message, budget, tokenizer.count_text)
        records.append(
            {
                "id": item["id"],
                "corpus_sha256": item["corpus_sha256"],
                "mode": "full_document" if full else "default_pack",
                "budget": budget,
                "original_tokens": tokenizer.count_text(message),
                "served_tokens": tokenizer.count_text(packed.text),
                "packed": packed.applied,
                "evidence_present": item["evidence_quote"] in packed.text,
            }
        )
    result = {
        "set": "compendium-20k-50",
        "kind": "offline_evidence_retention_only",
        "n": len(records),
        "evidence_present": sum(r["evidence_present"] for r in records),
        "packed_count": sum(r["packed"] for r in records),
        "records": records,
    }
    (HERE / "compendium-route-coverage.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(result["evidence_present"], "/", result["n"], "evidence quotes retained")


if __name__ == "__main__":
    audit()
