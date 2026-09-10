#!/usr/bin/env python3
"""Run Kiln image/video visual A/B. Writes gitignored files under runs/."""
from __future__ import annotations

import argparse
import json
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
SPEC = ROOT / "visual_ab.json"
API = "http://127.0.0.1:8787"


def _req(method: str, path: str, body: dict | None = None, timeout: int = 180):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get_content_type() == "application/json" or raw[:1] == b"{":
                return json.loads(raw.decode())
            return raw
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc


def _wait(job_id: str, timeout_s: int) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        last = _req("GET", f"/generate/{job_id}")
        if last.get("status") in {"done", "failed", "cancelled", "interrupted"}:
            return last
        time.sleep(4)
    raise TimeoutError(f"job {job_id} still {last.get('status')} after {timeout_s}s")


def _save_file(job: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = _req("GET", f"/generate/{job['id']}/file", timeout=120)
    if not isinstance(raw, (bytes, bytearray)):
        raise RuntimeError(f"expected bytes for {job['id']}")
    dest.write_bytes(raw)


def generate_image(item: dict, mode: str, seed: int, backend: str) -> dict:
    job = _req(
        "POST",
        "/generate",
        {
            "kind": "image",
            "prompt": item["prompt"],
            "prompt_mode": mode,
            "backend": backend,
            "seed": seed,
            "width": 1024,
            "height": 1024,
            "steps": 9,
        },
    )
    got = _wait(job["id"], 900)
    if got.get("status") != "done":
        raise RuntimeError(f"{item['id']} {mode} failed: {got.get('error')}")
    out = RUNS / "image" / f"{item['id']}-{mode}.png"
    _save_file(got, out)
    return {
        "id": item["id"],
        "mode": mode,
        "job_id": got["id"],
        "original_prompt": got.get("original_prompt") or item["prompt"],
        "effective_prompt": got.get("effective_prompt"),
        "seed": seed,
        "output": str(out.relative_to(ROOT)),
        "wall_s": (got.get("metrics") or {}).get("wall_s"),
        "status": got["status"],
        "constraints": item["constraints"],
    }


def generate_video(item: dict, preset: str, seed: int, backend: str) -> dict:
    job = _req(
        "POST",
        "/generate",
        {
            "kind": "video",
            "prompt": item["prompt"],
            "prompt_mode": "enhanced",
            "backend": backend,
            "seed": seed,
            "preset": preset,
        },
    )
    got = _wait(job["id"], 2400)
    if got.get("status") != "done":
        raise RuntimeError(f"{item['id']} {preset} failed: {got.get('error')}")
    out = RUNS / "video" / f"{item['id']}-{preset}.mp4"
    _save_file(got, out)
    return {
        "id": item["id"],
        "preset": preset,
        "job_id": got["id"],
        "original_prompt": got.get("original_prompt") or item["prompt"],
        "effective_prompt": got.get("effective_prompt"),
        "seed": seed,
        "output": str(out.relative_to(ROOT)),
        "wall_s": (got.get("metrics") or {}).get("wall_s"),
        "metrics": got.get("metrics") or {},
        "status": got["status"],
        "constraints": item["constraints"],
    }


def write_contact_sheet(rows: list[dict], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cards = []
    by_id: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_id.setdefault(row["id"], {})[row["mode"]] = row
    for item_id, pair in by_id.items():
        raw = pair.get("raw") or {}
        enh = pair.get("enhanced") or {}
        tr = pair.get("translate_enhance") or {}
        cards.append(
            f"""
<section>
  <h2>{item_id}</h2>
  <p><b>Original</b> {raw.get('original_prompt') or enh.get('original_prompt') or tr.get('original_prompt')}</p>
  <p><b>Effective (enhanced)</b> {enh.get('effective_prompt')}</p>
  <p><b>Effective (translate+enhance)</b> {tr.get('effective_prompt')}</p>
  <p>seed={raw.get('seed') or enh.get('seed') or tr.get('seed')}
     raw_wall={raw.get('wall_s')}s enhanced_wall={enh.get('wall_s')}s translate_wall={tr.get('wall_s')}s</p>
  <div class="pair">
    <figure><img src="{raw.get('output','')}" alt="raw"><figcaption>Raw</figcaption></figure>
    <figure><img src="{enh.get('output','')}" alt="enhanced"><figcaption>Enhanced</figcaption></figure>
    <figure><img src="{tr.get('output','')}" alt="translate"><figcaption>Translate+Enhance</figcaption></figure>
  </div>
</section>"""
        )
    dest.write_text(
        """<!doctype html><meta charset="utf-8"><title>Kiln visual A/B</title>
<style>
body{font:16px/1.4 ui-sans-serif,system-ui;margin:24px;max-width:1200px}
.pair{display:flex;gap:16px;flex-wrap:wrap}
img{max-width:480px;height:auto;background:#111}
p{white-space:pre-wrap}
</style>
<h1>Kiln image Raw vs Enhanced</h1>
"""
        + "\n".join(cards),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("image", "video", "all"), default="image")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--ids", default="")
    args = parser.parse_args()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    RUNS.mkdir(parents=True, exist_ok=True)
    manifest_path = RUNS / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {"image": [], "video": []}

    if args.kind in {"image", "all"}:
        items = spec["image"]
        if args.ids:
            wanted = set(args.ids.split(","))
            items = [x for x in items if x["id"] in wanted]
        else:
            items = items[args.offset : args.offset + args.limit]
        for item in items:
            for mode in ("raw", "enhanced", "translate_enhance"):
                out = RUNS / "image" / f"{item['id']}-{mode}.png"
                if out.is_file() and out.stat().st_size > 1000:
                    print(f"SKIP IMAGE {item['id']} {mode}", flush=True)
                    continue
                print(f"IMAGE {item['id']} {mode}", flush=True)
                row = generate_image(item, mode, spec["image_seed"], spec["image_backend"])
                manifest["image"] = [x for x in manifest["image"] if not (x["id"] == item["id"] and x["mode"] == mode)]
                manifest["image"].append(row)
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps({k: row[k] for k in ("id", "mode", "wall_s", "output")}, ensure_ascii=False), flush=True)
        write_contact_sheet(manifest["image"], RUNS / "contact-sheet.html")

    if args.kind in {"video", "all"}:
        items = spec["video"]
        if args.ids:
            wanted = set(args.ids.split(","))
            items = [x for x in items if x["id"] in wanted]
        else:
            items = items[args.offset : args.offset + args.limit]
        for item in items:
            for preset in ("fast", "standard"):
                out = RUNS / "video" / f"{item['id']}-{preset}.mp4"
                if out.is_file() and out.stat().st_size > 1000:
                    print(f"SKIP VIDEO {item['id']} {preset}", flush=True)
                    continue
                print(f"VIDEO {item['id']} {preset}", flush=True)
                row = generate_video(item, preset, spec["video_seed"], spec["video_backend"])
                manifest["video"] = [x for x in manifest["video"] if not (x["id"] == item["id"] and x["preset"] == preset)]
                manifest["video"].append(row)
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps({k: row[k] for k in ("id", "preset", "wall_s", "output")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
