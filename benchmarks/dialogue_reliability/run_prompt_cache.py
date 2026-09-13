#!/usr/bin/env python3
"""Minimal mlx-lm 0.31.3 prompt-cache experiment.

Talks to mlx-lm /v1/chat/completions directly (not Kiln /chat) so
chat_template_kwargs and streaming can be isolated from rolling fold.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RUNS = Path(__file__).resolve().parent / "runs"

SYSTEM = "你是简短中文对话伙伴。只回一句，不要解释。"
PREFIX = [
    {"role": "system", "content": SYSTEM},
    {"role": "user", "content": "钥匙还在你那儿吗？"},
    {"role": "assistant", "content": "还在，就放在抽屉第二层。"},
    {"role": "user", "content": "今晚能还我吗？"},
    {"role": "assistant", "content": "可以，我下班带回。"},
    {"role": "user", "content": "大概几点？"},
    {"role": "assistant", "content": "大概八点，我直接放到门口。"},
    {"role": "user", "content": "好。到时发我一下。"},
]

TURN_SLICES = [
    PREFIX[:2],
    PREFIX[:4],
    PREFIX[:6],
    PREFIX[:8],
]


def _sse_packets(raw: str) -> list[object]:
    out: list[object] = []
    for block in raw.replace("\r\n", "\n").split("\n\n"):
        data_lines = [
            line[5:].strip()
            for line in block.split("\n")
            if line.startswith("data:")
        ]
        data = "\n".join(data_lines)
        if not data:
            continue
        if data == "[DONE]":
            out.append("[DONE]")
            continue
        try:
            out.append(json.loads(data))
        except json.JSONDecodeError:
            out.append({"malformed": data})
    return out


def _usage_from(payload: dict) -> tuple[int, int, int]:
    usage = payload.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    return (
        int(usage.get("prompt_tokens") or 0),
        int(usage.get("completion_tokens") or 0),
        int(details.get("cached_tokens") or 0),
    )


def post_mlx(
    api: str,
    messages: list[dict],
    *,
    stream: bool,
    kwargs: dict | None,
    max_tokens: int,
    timeout: int,
) -> dict:
    body: dict = {
        "model": "default_model",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "stream": stream,
    }
    if stream:
        body["stream_options"] = {"include_usage": True}
    if kwargs is not None:
        body["chat_template_kwargs"] = kwargs
    req = urllib.request.Request(
        api.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    t0 = time.perf_counter()
    headers_s = None
    first_any_s = None
    first_visible_s = None
    raw = ""
    prompt = completion = cached = 0
    finish = None
    content = ""
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        headers_s = time.perf_counter() - t0
        if not stream:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
            total = time.perf_counter() - t0
            prompt, completion, cached = _usage_from(payload)
            choice = (payload.get("choices") or [{}])[0]
            finish = choice.get("finish_reason")
            msg = choice.get("message") or {}
            content = msg.get("content") or ""
            return {
                "stream": False,
                "headers_s": headers_s,
                "ttft_s": total,
                "probe_first_any_s": total,
                "probe_first_visible_s": total,
                "total_s": total,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "cached_tokens": cached,
                "cache_ratio": (cached / prompt) if prompt else 0.0,
                "decode_tok_s": None,
                "finish_reason": finish,
                "content_preview": content[:80],
            }
        while True:
            chunk = resp.read(256)
            if not chunk:
                break
            raw += chunk.decode("utf-8", "replace")
            now = time.perf_counter() - t0
            for item in _sse_packets(raw):
                if not isinstance(item, dict):
                    continue
                p, c, k = _usage_from(item)
                if p or c or k:
                    prompt, completion, cached = p, c, k
                choices = item.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                finish = choice.get("finish_reason") or finish
                delta = choice.get("delta") or {}
                text = delta.get("content") or ""
                reason = delta.get("reasoning") or delta.get("reasoning_content") or ""
                content += text
                if first_any_s is None and (text or reason):
                    first_any_s = now
                if first_visible_s is None and text:
                    first_visible_s = now
    total = time.perf_counter() - t0
    decode_s = None
    if first_any_s is not None and total > first_any_s and completion:
        decode_s = completion / (total - first_any_s)
    return {
        "stream": True,
        "headers_s": headers_s,
        "ttft_s": first_any_s,
        "probe_first_any_s": first_any_s,
        "probe_first_visible_s": first_visible_s,
        "total_s": total,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_tokens": cached,
        "cache_ratio": (cached / prompt) if prompt else 0.0,
        "decode_tok_s": decode_s,
        "finish_reason": finish,
        "content_preview": content[:80],
    }


def tokenize_matrix(model_path: str) -> list[dict]:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    variants = [
        ("undefined", {}),
        ("thinking_false", {"enable_thinking": False}),
        ("thinking_true", {"enable_thinking": True}),
        (
            "kiln_full_false",
            {
                "enable_thinking": False,
                "reasoning_effort": "medium",
                "preserve_thinking": False,
            },
        ),
        (
            "kiln_full_true",
            {
                "enable_thinking": True,
                "reasoning_effort": "medium",
                "preserve_thinking": False,
            },
        ),
    ]
    rows = []
    for name, kwargs in variants:
        raw_ids = tok.apply_chat_template(
            TURN_SLICES[0],
            add_generation_prompt=True,
            tokenize=True,
            **kwargs,
        )
        if hasattr(raw_ids, "input_ids"):
            raw_ids = raw_ids.input_ids
        elif isinstance(raw_ids, dict):
            raw_ids = raw_ids["input_ids"]
        if raw_ids and isinstance(raw_ids[0], list):
            raw_ids = raw_ids[0]
        ids = [int(x) for x in raw_ids]
        text = tok.apply_chat_template(
            TURN_SLICES[0],
            add_generation_prompt=True,
            tokenize=False,
            **kwargs,
        )
        rows.append(
            {
                "variant": name,
                "kwargs": kwargs,
                "n_tokens": len(ids),
                "ids": ids,
                "ids_head": ids[:16],
                "ids_tail": ids[-16:],
                "has_empty_think": "<think>\n\n</think>" in text,
                "has_open_think": text.endswith("<think>\n") or text.endswith("<think>\n\n"),
                "has_reasoning_instruction": "Reasoning effort is set" in text,
                "text_head": text[:180],
                "text_tail": text[-80:],
            }
        )
    return rows


def run_case(
    api: str,
    *,
    label: str,
    kwargs: dict | None,
    stream: bool,
    trials: int,
    turns: int,
    max_tokens: int,
    timeout: int,
) -> list[dict]:
    rows = []
    for trial in range(1, trials + 1):
        for turn in range(1, turns + 1):
            messages = TURN_SLICES[turn - 1]
            row = {
                "case": label,
                "trial": trial,
                "turn": turn,
                "request_kwargs": kwargs,
                "n_messages": len(messages),
            }
            try:
                row.update(
                    post_mlx(
                        api,
                        messages,
                        stream=stream,
                        kwargs=kwargs,
                        max_tokens=max_tokens,
                        timeout=timeout,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                row["error"] = str(exc)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8081")
    parser.add_argument("--model", default="/Users/rainhuang/Desktop/models/qwen3.5-9b-hauhau-aggressive-mxfp4")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-tokens", type=int, default=16)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--turns", type=int, default=3)
    parser.add_argument("--server-label", default="unknown")
    parser.add_argument(
        "--cases",
        default="",
        help="Comma list: A,B,C,D,live_nokw,live_false,live_true,kiln_full,persist_stream,persist_nostream",
    )
    parser.add_argument("--tokenize-only", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    token_rows = tokenize_matrix(args.model)
    if args.tokenize_only:
        out = RUNS / "prompt-cache-tokenize.json"
        RUNS.mkdir(parents=True, exist_ok=True)
        exact = {}
        for left in token_rows:
            for right in token_rows:
                exact[f"{left['variant']}=={right['variant']}"] = left["ids"] == right["ids"]
        slim = [{k: v for k, v in row.items() if k != "ids"} for row in token_rows]
        out.write_text(
            json.dumps(
                {
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "results": slim,
                    "exact_id_equal": exact,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "wrote": str(out),
                    "n_tokens": {r["variant"]: r["n_tokens"] for r in token_rows},
                    "has_reasoning_instruction": {
                        r["variant"]: r["has_reasoning_instruction"] for r in token_rows
                    },
                    "has_empty_think": {r["variant"]: r["has_empty_think"] for r in token_rows},
                    "exact_id_equal": exact,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    wanted = [p.strip() for p in args.cases.split(",") if p.strip()]
    catalog = {
        "A": None,
        "B": {"enable_thinking": False},
        "C": None,
        "D": {"enable_thinking": False},
        "live_nokw": None,
        "live_false": {"enable_thinking": False},
        "live_true": {"enable_thinking": True},
        "kiln_full": {
            "enable_thinking": False,
            "reasoning_effort": "medium",
            "preserve_thinking": False,
        },
    }
    rows: list[dict] = []
    for name in wanted:
        if name in {"persist_stream", "persist_nostream"}:
            stream = name == "persist_stream"
            rows.extend(
                run_case(
                    args.api,
                    label=name,
                    kwargs={"enable_thinking": False},
                    stream=stream,
                    trials=args.trials,
                    turns=4,
                    max_tokens=args.max_tokens,
                    timeout=args.timeout,
                )
            )
            continue
        if name not in catalog:
            raise SystemExit(f"unknown case {name}")
        rows.extend(
            run_case(
                args.api,
                label=name,
                kwargs=catalog[name],
                stream=True,
                trials=args.trials,
                turns=args.turns,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
            )
        )
        # One non-stream trial per named case for stream vs non-stream contrast.
        rows.extend(
            run_case(
                args.api,
                label=f"{name}_nostream",
                kwargs=catalog[name],
                stream=False,
                trials=1,
                turns=args.turns,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
            )
        )

    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "server_label": args.server_label,
        "tokenize": [{k: v for k, v in row.items() if k != "ids"} for row in token_rows],
        "results": rows,
    }
    out = Path(args.out) if args.out else RUNS / f"prompt-cache-{args.server_label}.json"
    RUNS.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
