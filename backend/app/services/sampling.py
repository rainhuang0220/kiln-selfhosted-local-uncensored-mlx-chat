"""Qwen3.5 sampling plus mlx-lm 0.31.3 adapter semantics."""

from __future__ import annotations

from typing import Any

# HuggingFace / official Qwen3.5 card.
THINKING = {
    "temperature": 0.6,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 0.0,
    "presence_context_size": 20,
    "frequency_penalty": 0.0,
    "frequency_context_size": 20,
    "repetition_penalty": 1.0,
    "repetition_context_size": 20,
}
NON_THINKING = {
    "temperature": 0.7,
    "top_p": 0.8,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 0.0,
    "presence_context_size": 20,
    "frequency_penalty": 0.0,
    "frequency_context_size": 20,
    "repetition_penalty": 1.0,
    "repetition_context_size": 20,
}

SAMPLING_KEYS = (
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "presence_penalty",
    "presence_context_size",
    "frequency_penalty",
    "frequency_context_size",
    "repetition_penalty",
    "repetition_context_size",
)


def mlx_repetition_penalty(value: float | None) -> float:
    """Map HF/Qwen repetition_penalty to mlx-lm.

    HuggingFace 1.0 means off. mlx-lm 0.31.3 also treats 0.0 as off, but a
    value of 1.0 *is* applied (logits / 1.0 or * 1.0). Sending 1.0 would
    pretend to match the card while changing nothing useful; we normalize
    1.0/0.0/None to mlx 0.0 so the adapter is explicit.
    """
    if value is None:
        return 0.0
    number = float(value)
    if number <= 0 or abs(number - 1.0) < 1e-9:
        return 0.0
    return number


def resolve_sampling(
    *,
    enable_thinking: bool,
    temperature: float | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    min_p: float | None = None,
    presence_penalty: float | None = None,
    presence_context_size: int | None = None,
    frequency_penalty: float | None = None,
    frequency_context_size: int | None = None,
    repetition_penalty: float | None = None,
    repetition_context_size: int | None = None,
    base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    preset = dict(base or (THINKING if enable_thinking else NON_THINKING))
    overrides = {
        "temperature": temperature,
        "top_p": top_p,
        "top_k": top_k,
        "min_p": min_p,
        "presence_penalty": presence_penalty,
        "presence_context_size": presence_context_size,
        "frequency_penalty": frequency_penalty,
        "frequency_context_size": frequency_context_size,
        "repetition_penalty": repetition_penalty,
        "repetition_context_size": repetition_context_size,
    }
    for key, value in overrides.items():
        if value is None:
            continue
        preset[key] = float(value) if key not in {"top_k", "presence_context_size", "frequency_context_size", "repetition_context_size"} else int(value)
    preset["top_k"] = int(preset["top_k"])
    for key in (
        "presence_context_size",
        "frequency_context_size",
        "repetition_context_size",
    ):
        preset[key] = int(preset[key])
    return {key: preset[key] for key in SAMPLING_KEYS}
