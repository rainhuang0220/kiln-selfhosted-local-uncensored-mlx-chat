#!/usr/bin/env python3
"""Live Continue / Regenerate / length-banner checks against /chat."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import RUNS, _delete, _post_chat


def main() -> None:
    api = "http://127.0.0.1:8787"
    rows = []
    first = _post_chat(
        api,
        {
            "message": "用很长的中文描写旧书店，不要停。",
            "stream": True,
            "enable_thinking": False,
            "max_tokens": 12,
            "profile": "interactive_dialogue",
        },
        120,
    )
    cid = first["conversation_id"]
    if not cid:
        raise SystemExit(f"length step did not return conversation_id: {first}")
    rows.append({"step": "length", **first})
    cont = _post_chat(
        api,
        {
            "message": "",
            "conversation_id": cid,
            "continue_generation": True,
            "stream": True,
            "enable_thinking": False,
            "max_tokens": 32,
            "profile": "interactive_dialogue",
        },
        120,
    )
    rows.append({"step": "continue", **cont})
    regen = _post_chat(
        api,
        {
            "message": "",
            "conversation_id": cid,
            "regenerate": True,
            "stream": True,
            "enable_thinking": False,
            "max_tokens": 24,
            "profile": "interactive_dialogue",
        },
        120,
    )
    rows.append({"step": "regenerate", **regen})
    stop = _post_chat(
        api,
        {
            "message": "只回一个字：好",
            "conversation_id": cid,
            "stream": True,
            "enable_thinking": False,
            "max_tokens": 64,
            "profile": "interactive_dialogue",
        },
        120,
    )
    rows.append({"step": "stop", **stop})
    import urllib.request

    detail = json.loads(
        urllib.request.urlopen(api + f"/conversation/{cid}", timeout=10).read().decode()
    )
    users = [m for m in detail["messages"] if m["role"] == "user"]
    assts = [m for m in detail["messages"] if m["role"] == "assistant"]
    report = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "steps": rows,
        "users": len(users),
        "assistants": len(assts),
        "user_contents": [m.get("content") for m in users],
        "length_finish": first.get("finish_reason"),
        "continue_grew": len(cont.get("content") or "") >= len(first.get("content") or ""),
        "no_fake_continue_user": all("continue" not in (m.get("content") or "").lower() for m in users),
        "stop_finish": stop.get("finish_reason"),
    }
    _delete(api, cid)
    out = RUNS / "continue-e2e.json"
    RUNS.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
