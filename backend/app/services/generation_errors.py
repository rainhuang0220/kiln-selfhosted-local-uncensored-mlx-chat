from dataclasses import dataclass
from typing import Any


class GenerationCancelled(Exception):
    """Raised when a generation job is cancelled at a safe point."""


@dataclass
class RunResult:
    output_path: str
    metrics: dict[str, Any]
