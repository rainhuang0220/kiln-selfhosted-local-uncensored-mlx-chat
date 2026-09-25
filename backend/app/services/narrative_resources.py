"""Memory / swap pressure sampling for narrative scheduling.

Does not restart or kill MLX. Pausing only blocks scheduling the next segment.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceSnapshot:
    swap_free_mib: float
    swapout_pages: int
    pages_free: int


@dataclass(frozen=True)
class PauseDecision:
    should_pause: bool
    reason: str | None = None
    snapshot: ResourceSnapshot | None = None


def sample_resources() -> ResourceSnapshot:
    vm = subprocess.check_output(["vm_stat"], text=True)
    swapouts = int(re.search(r"Swapouts:\s+(\d+)", vm).group(1))
    pages_free = int(re.search(r"Pages free:\s+(\d+)\.", vm).group(1))
    usage = subprocess.check_output(["sysctl", "vm.swapusage"], text=True)
    free = float(re.search(r"free = ([\d.]+)M", usage).group(1))
    return ResourceSnapshot(
        swap_free_mib=free,
        swapout_pages=swapouts,
        pages_free=pages_free,
    )


def should_pause_for_resources(
    snap: ResourceSnapshot | None = None,
    *,
    min_free_mib: float = 256.0,
    min_pages_free: int = 20_000,
) -> PauseDecision:
    """Pause next-segment scheduling when free swap (or free RAM pages) is too low.

    Cumulative Swapouts alone are not a pause signal — they grow over machine
    lifetime and previously caused a false abort near ~18K visible chars while
    free swap was still healthy.
    """
    snapshot = snap or sample_resources()
    if snapshot.swap_free_mib < min_free_mib:
        return PauseDecision(True, "low_swap_free", snapshot)
    if snapshot.pages_free < min_pages_free:
        return PauseDecision(True, "low_pages_free", snapshot)
    return PauseDecision(False, None, snapshot)
