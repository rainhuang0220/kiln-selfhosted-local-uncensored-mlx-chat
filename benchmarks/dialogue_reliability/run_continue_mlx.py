#!/usr/bin/env python3
"""Probe mlx-lm 0.31.3 continuation paths. Talks to :8081 only."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from transformers import AutoTokenizer

MODEL = "/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4"
MLX = "http://127.0.0.1:8081"
RUNS = Path(__file__).resolve().parent / "runs"
USER = "用四个汉字描写雨停。"


def _post(path: str, body: dict, timeout: float = 90) -> dict:
    req = urllib.request.Request(
        MLX + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            elapsed = time.perf_counter() - started
            if body.get("stream"):
                text = ""
                usage = {}
                finish = None
                for block in raw.split("\n\n"):
                    line = block.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        continue
                    try:
                        ev = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    usage = ev.get("usage") or usage
                    choice = (ev.get("choices") or [{}])[0]
                    finish = choice.get("finish_reason") or finish
                    delta = choice.get("delta") or {}
                    text += delta.get("content") or choice.get("text") or ""
                return {
                    "ok": True,
                    "elapsed_s": round(elapsed, 3),
                    "content": text,
                    "finish": finish,
                    "usage": usage,
                    "status": resp.status,
                }
            data = json.loads(raw)
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            return {
                "ok": True,
                "elapsed_s": round(elapsed, 3),
                "content": msg.get("content") or choice.get("text") or "",
                "finish": choice.get("finish_reason"),
                "usage": data.get("usage") or {},
                "status": resp.status,
            }
    except urllib.error.HTTPError as exc:
        elapsed = time.perf_counter() - started
        err = exc.read().decode("utf-8", errors="replace")[:800]
        return {
            "ok": False,
            "elapsed_s": round(elapsed, 3),
            "status": exc.code,
            "error": err,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "elapsed_s": round(time.perf_counter() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _health() -> dict:
    try:
        with urllib.request.urlopen(MLX + "/health", timeout=3) as resp:
            return {"ok": resp.status == 200, "body": resp.read().decode()[:200]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _usage_row(label: str, result: dict) -> dict:
    usage = result.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    cached = int(details.get("cached_tokens") or 0)
    return {
        "label": label,
        "ok": result.get("ok"),
        "status": result.get("status"),
        "error": result.get("error"),
        "elapsed_s": result.get("elapsed_s"),
        "content": result.get("content"),
        "finish": result.get("finish"),
        "prompt_tokens": prompt,
        "cached_tokens": cached,
        "cache_ratio": round(cached / prompt, 3) if prompt else None,
        "completion_tokens": usage.get("completion_tokens"),
    }


def main() -> None:
    tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
    rows = []

    local = {}
    try:
        tok.apply_chat_template(
            [{"role": "user", "content": USER}, {"role": "assistant", "content": "雨停了，"}],
            tokenize=False,
            add_generation_prompt=True,
            continue_final_message=True,
            enable_thinking=False,
        )
        local["continue_plus_gen_prompt"] = "accepted"
    except Exception as exc:  # noqa: BLE001
        local["continue_plus_gen_prompt"] = f"{type(exc).__name__}: {exc}"

    native = tok.apply_chat_template(
        [{"role": "user", "content": USER}, {"role": "assistant", "content": "雨停了，"}],
        tokenize=False,
        add_generation_prompt=False,
        continue_final_message=True,
        enable_thinking=False,
    )
    closed = tok.apply_chat_template(
        [{"role": "user", "content": USER}, {"role": "assistant", "content": "雨停了，"}],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    local["native_continue"] = native
    local["last_assistant_plus_gen_prompt"] = closed
    local["native_is_open"] = not native.rstrip().endswith("<|im_end|>")
    local["closed_starts_new_assistant"] = closed.rstrip().endswith(
        "<|im_start|>assistant"
    ) or closed.count("<|im_start|>assistant") >= 2

    rows.append(
        _usage_row(
            "A_chat_continue_and_add_false",
            _post(
                "/v1/chat/completions",
                {
                    "model": "default_model",
                    "messages": [
                        {"role": "user", "content": USER},
                        {"role": "assistant", "content": "雨停了，"},
                    ],
                    "max_tokens": 8,
                    "stream": False,
                    "temperature": 0.7,
                    "chat_template_kwargs": {
                        "enable_thinking": False,
                        "continue_final_message": True,
                        "add_generation_prompt": False,
                    },
                },
            ),
        )
    )
    rows.append(
        _usage_row(
            "B_chat_continue_only",
            _post(
                "/v1/chat/completions",
                {
                    "model": "default_model",
                    "messages": [
                        {"role": "user", "content": USER},
                        {"role": "assistant", "content": "雨停了，"},
                    ],
                    "max_tokens": 8,
                    "stream": False,
                    "temperature": 0.7,
                    "chat_template_kwargs": {
                        "enable_thinking": False,
                        "continue_final_message": True,
                    },
                },
            ),
        )
    )
    rows.append(
        _usage_row(
            "C_chat_last_assistant_no_continue",
            _post(
                "/v1/chat/completions",
                {
                    "model": "default_model",
                    "messages": [
                        {"role": "user", "content": USER},
                        {"role": "assistant", "content": "雨停了，"},
                    ],
                    "max_tokens": 8,
                    "stream": False,
                    "temperature": 0.7,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            ),
        )
    )

    seed = _post(
        "/v1/chat/completions",
        {
            "model": "default_model",
            "messages": [{"role": "user", "content": USER}],
            "max_tokens": 12,
            "stream": True,
            "temperature": 0.7,
            "chat_template_kwargs": {"enable_thinking": False},
        },
    )
    rows.append(_usage_row("seed_stream", seed))
    partial = (seed.get("content") or "").strip() or "雨停了，"
    cont_msgs = [
        {"role": "user", "content": USER},
        {"role": "assistant", "content": partial},
    ]
    native_full = tok.apply_chat_template(
        cont_msgs,
        tokenize=False,
        add_generation_prompt=False,
        continue_final_message=True,
        enable_thinking=False,
    )
    ids = tok.encode(native_full, add_special_tokens=False)
    trimmed = tok.decode(ids[:-1], skip_special_tokens=False)
    extra = native_full  # exact cached prefix; used last because it can crash the server

    rows.append(
        _usage_row(
            "E_completions_trimmed_last_token",
            _post(
                "/v1/completions",
                {
                    "model": "default_model",
                    "prompt": trimmed,
                    "max_tokens": 8,
                    "stream": True,
                    "temperature": 0.7,
                },
            ),
        )
    )
    rows.append(
        _usage_row(
            "F_completions_plus_trailing_space",
            _post(
                "/v1/completions",
                {
                    "model": "default_model",
                    "prompt": native_full + " ",
                    "max_tokens": 8,
                    "stream": True,
                    "temperature": 0.7,
                },
            ),
        )
    )
    rows.append(
        _usage_row(
            "D_completions_exact_native",
            _post(
                "/v1/completions",
                {
                    "model": "default_model",
                    "prompt": extra,
                    "max_tokens": 8,
                    "stream": True,
                    "temperature": 0.7,
                },
            ),
        )
    )
    time.sleep(0.5)
    health_after_d = _health()
    models_after_d = _post(
        "/v1/chat/completions",
        {
            "model": "default_model",
            "messages": [{"role": "user", "content": "只回一个字：好"}],
            "max_tokens": 4,
            "stream": False,
            "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False},
        },
    )

    report = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "mlx_lm": "0.31.3",
        "local_tokenizer": local,
        "native_full": native_full,
        "trimmed": trimmed,
        "dropped_tail": tok.decode([ids[-1]], skip_special_tokens=False),
        "rows": rows,
        "health_after_exact_continue": health_after_d,
        "generate_after_exact_continue": _usage_row("post_d_generate", models_after_d),
    }
    RUNS.mkdir(parents=True, exist_ok=True)
    out = RUNS / "continue-mlx-paths.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
