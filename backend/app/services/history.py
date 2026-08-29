from typing import Callable


Estimate = Callable[[str], int]


def _text_of(message: dict) -> str:
    content = message.get("content") or ""
    reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
    if reasoning:
        return f"{reasoning}\n{content}"
    return content


def truncate_messages(
    messages: list[dict],
    budget: int,
    estimate: Estimate,
    reserved_output: int = 0,
) -> tuple[list[dict], list[str], bool]:
    """Drop oldest user/assistant/tool turns. Never drop system or the latest user.

    Returns (kept, dropped_ids, truncated).
    """
    if not messages:
        return [], [], False

    limit = max(1, budget - max(0, reserved_output))

    system = [m for m in messages if m.get("role") == "system"][:1]
    rest = [m for m in messages if m.get("role") != "system"]
    if not rest:
        return system, [], False

    latest = rest[-1]
    body = rest[:-1]

    def total(ms: list[dict]) -> int:
        return sum(estimate(_text_of(m)) for m in ms)

    kept_body = list(body)
    dropped: list[str] = []
    candidate = system + kept_body + [latest]

    while kept_body and total(candidate) > limit:
        removed = kept_body.pop(0)
        dropped.append(str(removed.get("id") or ""))
        # drop a following assistant/tool that belonged to that user turn
        while kept_body and kept_body[0].get("role") in {"assistant", "tool"}:
            extra = kept_body.pop(0)
            dropped.append(str(extra.get("id") or ""))
        candidate = system + kept_body + [latest]

    truncated = bool(dropped)
    dropped = [d for d in dropped if d]
    return candidate, dropped, truncated
