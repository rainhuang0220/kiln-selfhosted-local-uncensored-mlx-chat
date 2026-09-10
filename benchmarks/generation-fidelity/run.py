#!/usr/bin/env python3
"""List the public fidelity prompts. Does not generate media."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    data = json.loads((ROOT / "prompts.json").read_text(encoding="utf-8"))
    if args.list:
        for item in data["items"]:
            print(f"{item['id']}\t{item['kind']}\t{item['prompt']}")
        return
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
