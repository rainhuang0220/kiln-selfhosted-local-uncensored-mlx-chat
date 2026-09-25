"""Offline counters + continuity probes for narrative acceptance."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.narrative_chars import count_han, count_visible_chars  # noqa: E402
from app.services.narrative_continuity import check_segment  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: score_visible.py <text-file>")
        return 2
    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    report = check_segment(text, min_chars=1000)
    out = {
        "visible_chars": count_visible_chars(text),
        "han_chars": count_han(text),
        "raw_chars": len(text),
        "continuity_ok": report.ok,
        "continuity_reasons": report.reasons,
        "repeat_ratio": report.repeat_ratio,
        "agency_hits": report.agency_hits,
        "pass_ge_20000": count_visible_chars(text) >= 20000,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["pass_ge_20000"] and report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
