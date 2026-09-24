#!/usr/bin/env python3
"""mlx-lm 0.31.3 prompt-cache hit/miss and exact-hit dead thread.

Exits immediately unless KILN_ALLOW_REPRO=1. Does not import mlx and does not
load weights on the refuse path. When allowed, it POSTs to the MLX server.

The exact-hit phase kills mlx_lm.server's generation thread. On the installed
0.31.3, GET /health stays 200 afterwards and later completions hang. Do not
point this at PID 1581 unless the orchestrator holds the GPU lock and already
plans a restart.

Env:
  KILN_ALLOW_REPRO=1          required
  KILN_REPRO_URL              default http://127.0.0.1:8081
  KILN_REPRO_MODEL            local tokenizer dir; default is the live 9B path
  KILN_REPRO_TIMEOUT_S        per-request timeout for healthy calls (default 90)
  KILN_REPRO_HANG_TIMEOUT_S   timeout that defines "hung" (default 20)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid


def _refuse() -> int:
    print(
        "refusing: KILN_ALLOW_REPRO is not 1; not sending any generation request",
        file=sys.stderr,
    )
    return 0


def _cached(usage: dict) -> int | None:
    details = usage.get("prompt_tokens_details") or {}
    if "cached_tokens" not in details:
        return None
    return int(details.get("cached_tokens") or 0)


def _post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            elapsed = time.perf_counter() - started
            if body.get("stream"):
                text = ""
                usage: dict = {}
                saw_done = False
                for block in raw.split("\n\n"):
                    line = block.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        saw_done = True
                        continue
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    usage = event.get("usage") or usage
                    choice = (event.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    text += choice.get("text") or delta.get("content") or ""
                return {
                    "ok": True,
                    "status": resp.status,
                    "elapsed_s": round(elapsed, 3),
                    "text": text,
                    "usage": usage,
                    "saw_done": saw_done,
                    "hung": False,
                }
            data = json.loads(raw)
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            ids = []
            content = (choice.get("logprobs") or {}).get("content") or []
            for item in content:
                if isinstance(item, dict) and "id" in item:
                    ids.append(int(item["id"]))
            return {
                "ok": True,
                "status": resp.status,
                "elapsed_s": round(elapsed, 3),
                "text": message.get("content") or choice.get("text") or "",
                "usage": data.get("usage") or {},
                "token_ids": ids,
                "hung": False,
            }
    except TimeoutError as exc:
        return {
            "ok": False,
            "hung": True,
            "elapsed_s": round(time.perf_counter() - started, 3),
            "error": f"timeout: {exc}",
        }
    except urllib.error.URLError as exc:
        timed_out = isinstance(exc.reason, TimeoutError) or "timed out" in str(exc).lower()
        return {
            "ok": False,
            "hung": timed_out,
            "elapsed_s": round(time.perf_counter() - started, 3),
            "error": str(exc),
        }


def _get(url: str, timeout: float = 5) -> dict:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status": resp.status,
                "body": body[:200],
                "elapsed_s": round(time.perf_counter() - started, 3),
            }
    except Exception as exc:  # noqa: BLE001 — report transport, do not hide it
        return {
            "ok": False,
            "error": str(exc),
            "elapsed_s": round(time.perf_counter() - started, 3),
        }


def _emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def _load_tokenizer(model: str):
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(model, local_files_only=True, trust_remote_code=False)


def main() -> int:
    if os.environ.get("KILN_ALLOW_REPRO") != "1":
        return _refuse()

    base = os.environ.get("KILN_REPRO_URL", "http://127.0.0.1:8081").rstrip("/")
    model = os.environ.get(
        "KILN_REPRO_MODEL",
        "/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4",
    )
    timeout = float(os.environ.get("KILN_REPRO_TIMEOUT_S", "90"))
    hang_timeout = float(os.environ.get("KILN_REPRO_HANG_TIMEOUT_S", "20"))
    nonce = uuid.uuid4().hex[:12]
    system = f"KILN_REPRO_SYS_{nonce}. Reply with one short word."
    chat = base + "/v1/chat/completions"
    comp = base + "/v1/completions"

    _emit("health_before", **_get(base + "/health"))

    def chat_call(user: str, system_text: str) -> dict:
        out = _post(
            chat,
            {
                "model": "default_model",
                "messages": [
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 8,
                "temperature": 0,
                "stream": False,
            },
            timeout,
        )
        usage = out.get("usage") or {}
        out["cached_tokens"] = _cached(usage)
        out["prompt_tokens"] = usage.get("prompt_tokens")
        return out

    first = chat_call("alpha", system)
    second = chat_call("beta", system)
    novel = chat_call("gamma", f"KILN_REPRO_SYS_OTHER_{nonce}. Reply with one short word.")
    _emit(
        "cache_hit_miss",
        nonce=nonce,
        first_cached=first.get("cached_tokens"),
        first_prompt=first.get("prompt_tokens"),
        second_cached=second.get("cached_tokens"),
        second_prompt=second.get("prompt_tokens"),
        novel_cached=novel.get("cached_tokens"),
        novel_prompt=novel.get("prompt_tokens"),
        first_ok=first.get("ok"),
        second_ok=second.get("ok"),
        novel_ok=novel.get("ok"),
        note=(
            "Qwen3.5 hybrid cache cannot trim a longer entry. "
            "A same-system second turn should show cached_tokens > 0 and "
            "< prompt_tokens. A new system should be 0. "
            "cached_tokens == prompt_tokens is an exact hit and is the crash shape."
        ),
    )

    try:
        tokenizer = _load_tokenizer(model)
    except Exception as exc:  # noqa: BLE001
        _emit("exact_hit_skipped", error=f"tokenizer unavailable: {exc}")
        _emit("health_after", **_get(base + "/health"))
        return 1

    prompt = f"KILN_REPRO_EXACT_{nonce} alpha beta gamma"
    prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)
    seeded = _post(
        comp,
        {
            "model": "default_model",
            "prompt": prompt,
            "max_tokens": 4,
            "temperature": 0,
            "stream": False,
            "logprobs": True,
        },
        timeout,
    )
    completion_ids = seeded.get("token_ids") or []
    if not seeded.get("ok") or not completion_ids:
        _emit("exact_seed_failed", result={k: seeded.get(k) for k in ("ok", "error", "status", "usage")})
        _emit("health_after", **_get(base + "/health"))
        return 1

    exact = tokenizer.decode(list(prompt_ids) + list(completion_ids), skip_special_tokens=False)
    replay = _post(
        comp,
        {
            "model": "default_model",
            "prompt": exact,
            "max_tokens": 4,
            "temperature": 0,
            "stream": True,
            "stream_options": {"include_usage": True},
        },
        hang_timeout,
    )
    probe = _post(
        comp,
        {
            "model": "default_model",
            "prompt": f"KILN_REPRO_PROBE_{nonce}",
            "max_tokens": 1,
            "temperature": 0,
            "stream": False,
        },
        hang_timeout,
    )
    health_after = _get(base + "/health")
    _emit(
        "exact_hit_hang",
        seed_cached=_cached(seeded.get("usage") or {}),
        seed_prompt_tokens=(seeded.get("usage") or {}).get("prompt_tokens"),
        completion_tokens=len(completion_ids),
        replay_hung=bool(replay.get("hung")),
        replay_ok=replay.get("ok"),
        replay_error=replay.get("error"),
        replay_cached=_cached(replay.get("usage") or {}),
        probe_hung=bool(probe.get("hung")),
        probe_ok=probe.get("ok"),
        probe_error=probe.get("error"),
        health_after=health_after,
        installed_0_31_3_signature=(
            bool(replay.get("hung"))
            and bool(probe.get("hung"))
            and health_after.get("status") == 200
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
