"""Split TTFT from decode throughput. Never call total elapsed tok/s 'decode tok/s'."""

from __future__ import annotations

from typing import Any


def compute_generation_metrics(
    *,
    output_tokens: int,
    elapsed_s: float | None,
    ttft_s: float | None,
    prompt_tokens: int = 0,
    cached_tokens: int = 0,
    thinking_tokens: int = 0,
    visible_tokens: int = 0,
    first_any_s: float | None = None,
) -> dict[str, Any]:
    effective = None
    decode = None
    if elapsed_s and elapsed_s > 0 and output_tokens:
        effective = output_tokens / elapsed_s
    decode_s = None
    if first_any_s is not None and elapsed_s is not None and elapsed_s > first_any_s:
        decode_s = elapsed_s - first_any_s
    elif ttft_s is not None and elapsed_s is not None and elapsed_s > ttft_s:
        decode_s = elapsed_s - ttft_s
    if decode_s and output_tokens:
        decode = output_tokens / decode_s
    return {
        "ttft_ms": int(ttft_s * 1000) if ttft_s is not None else None,
        "total_latency_ms": int(elapsed_s * 1000) if elapsed_s is not None else None,
        "effective_output_tokens_per_sec": effective,
        "decode_tokens_per_sec": decode,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "cache_hit_ratio": (cached_tokens / prompt_tokens) if prompt_tokens else None,
        "thinking_tokens": thinking_tokens,
        "visible_tokens": visible_tokens,
    }
