import re
from dataclasses import dataclass
from typing import Any


FIRST_TOKEN_IDLE_S = 45.0
BETWEEN_TOKEN_IDLE_S = 20.0
GENERATION_IDLE = "生成无响应"
PROVIDER_BUSY = "本机模型忙碌，请稍后再试"

_BUSY_CAUSES = re.compile(
    r"mlx timeout|mlx unreachable|mlx error (?:401|404|429|503)|Repository Not Found"
    r"|upstream stream ended before a reliable terminal",
    re.I,
)


def user_generation_error(error: str | None, *, had_output: bool) -> str | None:
    """Before any token, a dead / queued / Hub-erroring local model reads as busy."""
    if error and not had_output and _BUSY_CAUSES.search(error):
        return PROVIDER_BUSY
    return error


class GenerationCancelled(Exception):
    """Raised when a generation job is cancelled at a safe point."""


@dataclass
class RunResult:
    output_path: str
    metrics: dict[str, Any]
