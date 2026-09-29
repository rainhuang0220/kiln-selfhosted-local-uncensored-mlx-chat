"""Build two fixed long-document corpora from the existing semantic 50 items.

The source items, order, and section labels are immutable inputs. This creates
a paired evaluation set; it does not change the earlier short-document scores.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def build() -> None:
    rows = [json.loads(line) for line in (HERE / "longdoc-50.jsonl").read_text().splitlines()]
    assert len(rows) == 50
    tasks = []
    # Overlap six source sections so both fixed corpora exceed 20K model tokens.
    # Each scored item still belongs to exactly one corpus.
    groups = ((rows[:27], rows[:25]), (rows[21:], rows[25:]))
    for index, (group, scored) in enumerate(groups, start=1):
        corpus_id = f"semantic-compendium-{index}"
        corpus_file = f"{corpus_id}.txt"
        sections = []
        offsets = {}
        cursor = 0
        for row in group:
            section = f"[{row['id']}]\n{row['document']}\n"
            offsets[row["id"]] = (cursor, cursor + len(section))
            sections.append(section)
            cursor += len(section) + 1
        corpus = "\n".join(sections)
        assert len(corpus) >= 20_000
        digest = hashlib.sha256(corpus.encode("utf-8")).hexdigest()
        (HERE / corpus_file).write_text(corpus)
        for row in scored:
            start, end = offsets[row["id"]]
            local = corpus[start:end].find(row["evidence_quote"])
            assert local >= 0, row["id"]
            evidence_start = start + local
            evidence_end = evidence_start + len(row["evidence_quote"])
            assert corpus[evidence_start:evidence_end] == row["evidence_quote"]
            tasks.append(
                {
                    "id": row["id"],
                    "corpus_id": corpus_id,
                    "corpus_file": corpus_file,
                    "corpus_sha256": digest,
                    "corpus_chars": len(corpus),
                    "question": f"在章节 [{row['id']}] 中，{row['question']}",
                    "answer": row["answer"],
                    "evidence_quote": row["evidence_quote"],
                    "evidence_start": evidence_start,
                    "evidence_end": evidence_end,
                    "section_start": start,
                    "section_end": end,
                    "task": row["task"],
                    "needs_full_text": row["needs_full_text"],
                    "scoring_rule": "strict answer text; also grade numeric value, unit, and quote completeness separately",
                }
            )
    target = HERE / "compendium-20k-50.jsonl"
    target.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in tasks) + "\n")
    print(target.name, len(tasks))


if __name__ == "__main__":
    build()
