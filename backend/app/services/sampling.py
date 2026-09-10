"""Qwen3.5 recommended sampling. Thinking and non-thinking are different presets."""

from __future__ import annotations

from typing import Any

# From the Hauhau / official Qwen3.5 model card.
THINKING = {"temperature": 0.6, "top_p": 0.95, "top_k": 20}
NON_THINKING = {"temperature": 0.7, "top_p": 0.8, "top_k": 20}


def resolve_sampling(
    *,
    enable_thinking: bool,
    temperature: float | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
) -> dict[str, Any]:
    preset = THINKING if enable_thinking else NON_THINKING
    return {
        "temperature": preset["temperature"] if temperature is None else float(temperature),
        "top_p": preset["top_p"] if top_p is None else float(top_p),
        "top_k": preset["top_k"] if top_k is None else int(top_k),
    }
