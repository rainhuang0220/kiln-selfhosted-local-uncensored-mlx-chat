"""One short generation recorded by Kiln itself.

This is not the /health handler. Callers must rate-limit it. A busy queue
skips the probe instead of being reported as a dead generator.
"""

from __future__ import annotations

from pathlib import Path

from app.providers.base import ChatRequest

PROBE_FLAG = Path("/tmp/kiln-readiness-probe-once")
_PROBE_MESSAGE = "Reply with exactly kiln-ok"


async def run_readiness_probe(chat, *, busy: bool | None = None) -> str:
    if busy is None:
        busy = bool(getattr(chat, "_busy", None))
    if busy:
        return "skipped_busy"
    request = ChatRequest(
        messages=[{"role": "user", "content": _PROBE_MESSAGE}],
        temperature=0.0,
        top_p=1.0,
        top_k=1,
        max_tokens=16,
        enable_thinking=False,
    )
    try:
        result = await chat.provider.complete(request)
    except TimeoutError as exc:
        chat.note_inference_timeout(str(exc))
        return "degraded"
    except Exception as exc:
        message = str(exc)
        if "thread" in message.lower() or "not alive" in message.lower():
            chat.watch.note_thread_dead(message)
            return "failed"
        chat.note_inference_failure(message)
        return "degraded"
    if result.finish_reason in {"stop", "length"} and (result.content or "").strip():
        chat.note_inference_success("probe")
        return "ready"
    chat.note_inference_failure("probe returned no completion")
    return "degraded"


async def consume_probe_flag(chat, flag: Path = PROBE_FLAG) -> str | None:
    if not flag.is_file():
        return None
    flag.unlink(missing_ok=True)
    return await run_readiness_probe(chat)
