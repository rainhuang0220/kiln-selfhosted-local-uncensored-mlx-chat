#!/usr/bin/env python3
"""Aggregate constraint scores. Does not look at pixels; judges come from a filled card."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def rate(card: dict) -> tuple[int, int, int, int, float]:
    rows = card.get("constraints") or []
    total = len(rows)
    sat = sum(1 for r in rows if r.get("verdict") == "PASS")
    fail = sum(1 for r in rows if r.get("verdict") == "FAIL")
    unc = sum(1 for r in rows if r.get("verdict") == "UNCERTAIN")
    return sat, fail, unc, total, (sat / total if total else 0.0)


def axis_rates(cards: list[dict]) -> dict[str, float]:
    sat: dict[str, int] = defaultdict(int)
    tot: dict[str, int] = defaultdict(int)
    for card in cards:
        for row in card.get("constraints") or []:
            axis = row.get("axis") or "other"
            tot[axis] += 1
            if row.get("verdict") == "PASS":
                sat[axis] += 1
    return {k: (sat[k] / tot[k] if tot[k] else 0.0) for k in sorted(tot)}


def mean_adherence(cards: list[dict]) -> float:
    if not cards:
        return 0.0
    return sum(rate(c)[4] for c in cards) / len(cards)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scores_json")
    args = parser.parse_args()
    data = json.loads(Path(args.scores_json).read_text(encoding="utf-8"))
    groups: dict[str, list[dict]] = defaultdict(list)
    for card in data.get("items") or []:
        groups[str(card.get("mode") or card.get("preset") or "?")].append(card)
    print(json.dumps(
        {
            name: {
                "n": len(cards),
                "mean_adherence": round(mean_adherence(cards), 4),
                "axes": {k: round(v, 4) for k, v in axis_rates(cards).items()},
                "mean_wall_s": round(
                    sum(float(c.get("wall_s") or 0) for c in cards) / len(cards),
                    3,
                ) if cards else 0,
            }
            for name, cards in groups.items()
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
