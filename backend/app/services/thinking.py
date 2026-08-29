import re

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_UNCLOSED_RE = re.compile(r"<think>(.*)$", re.DOTALL | re.IGNORECASE)


def split_thinking(text: str) -> tuple[str, str]:
    """Return (visible_content, reasoning)."""
    if not text:
        return "", ""
    match = _THINK_RE.search(text)
    if match:
        reasoning = match.group(1).strip()
        content = _THINK_RE.sub("", text, count=1).strip()
        return content, reasoning
    unclosed = _UNCLOSED_RE.search(text)
    if unclosed:
        return "", unclosed.group(1).strip()
    return text, ""


def remap_assistant_for_history(message: dict) -> dict:
    """mlx streams `reasoning`; Qwen template reads `reasoning_content`."""
    out = {k: v for k, v in message.items() if k != "reasoning"}
    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
    if reasoning:
        out["reasoning_content"] = reasoning
    return out


def normalize_effort(value: str | None) -> str:
    if not value:
        return "medium"
    v = value.lower().strip()
    if v in {"high", "max"}:
        return "xhigh"
    if v in {"mid", "median"}:
        return "medium"
    if v in {"xhigh", "medium", "low"}:
        return v
    return "medium"


# Hard cap on reasoning tokens. 0 = unlimited (xhigh / max).
# low is ≥2× below a typical 512-token “low” budget; medium is the midpoint.
THINKING_BUDGET = {"low": 256, "medium": 1024, "xhigh": 0}


def thinking_budget_for(
    effort: str | None,
    *,
    low: int | None = None,
    medium: int | None = None,
    xhigh: int | None = None,
) -> int | None:
    resolved = normalize_effort(effort)
    table = {
        "low": THINKING_BUDGET["low"] if low is None else low,
        "medium": THINKING_BUDGET["medium"] if medium is None else medium,
        "xhigh": THINKING_BUDGET["xhigh"] if xhigh is None else xhigh,
    }
    n = int(table[resolved])
    return n if n > 0 else None
