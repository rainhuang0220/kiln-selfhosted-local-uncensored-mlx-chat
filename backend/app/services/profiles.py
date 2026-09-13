"""First-class generation profiles. Public names stay professional."""

from __future__ import annotations

from typing import Any

# Interactive Dialogue defaults are anchored on the Qwen3.5 non-thinking card,
# then adjusted from local A/B (see benchmarks/dialogue_reliability/).
# repetition_penalty uses HuggingFace/Qwen scale: 1.0 means off.
INTERACTIVE_DIALOGUE = {
    "profile": "interactive_dialogue",
    "enable_thinking": False,
    "reasoning_effort": "medium",
    "thinking_continuation": False,
    "max_tokens": 1536,
    "temperature": 0.7,
    "top_p": 0.8,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 0.5,
    "presence_context_size": 256,
    "frequency_penalty": 0.0,
    "frequency_context_size": 256,
    "repetition_penalty": 1.0,
    "repetition_context_size": 128,
    "prompt_soft_target": 8192,
    "prompt_budget": 10240,
}

BALANCED = {
    **INTERACTIVE_DIALOGUE,
    "profile": "balanced",
    "max_tokens": 4096,
    "presence_penalty": 0.0,
    "temperature": 0.7,
    "top_p": 0.9,
    "prompt_soft_target": 12288,
    "prompt_budget": 16384,
}

REASONING = {
    "profile": "reasoning",
    "enable_thinking": True,
    "reasoning_effort": "medium",
    "thinking_continuation": False,
    "max_tokens": 8192,
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
    "prompt_soft_target": 16384,
    "prompt_budget": 32768,
}

PROFILES: dict[str, dict[str, Any]] = {
    "interactive_dialogue": INTERACTIVE_DIALOGUE,
    "conversational": INTERACTIVE_DIALOGUE,
    "balanced": BALANCED,
    "reasoning": REASONING,
}

DEFAULT_PROFILE = "interactive_dialogue"


def normalize_profile(name: str | None) -> str:
    if not name:
        return DEFAULT_PROFILE
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "dialogue": "interactive_dialogue",
        "chat": "interactive_dialogue",
        "think": "reasoning",
        "thinking": "reasoning",
    }
    key = aliases.get(key, key)
    if key not in PROFILES:
        return DEFAULT_PROFILE
    return "interactive_dialogue" if key == "conversational" else key


def resolve_profile(name: str | None) -> dict[str, Any]:
    return dict(PROFILES[normalize_profile(name)])
