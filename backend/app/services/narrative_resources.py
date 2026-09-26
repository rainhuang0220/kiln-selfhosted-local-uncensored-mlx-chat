"""Memory / swap pressure sampling for narrative scheduling.

Does not restart or kill MLX. Pausing only blocks scheduling the next segment.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceSnapshot:
    swap_free_mib: float
    swapout_pages: int
    pages_free: int
    known: bool = True


@dataclass(frozen=True)
class PauseDecision:
    should_pause: bool
    reason: str | None = None
    snapshot: ResourceSnapshot | None = None


def _unknown_snapshot() -> ResourceSnapshot:
    return ResourceSnapshot(
        swap_free_mib=10_000.0,
        swapout_pages=0,
        pages_free=10_000_000,
        known=False,
    )


def sample_resources() -> ResourceSnapshot:
    """Sample swap/RAM. Never raises FileNotFoundError on Linux / missing tools."""
    if sys.platform != "darwin":
        return _unknown_snapshot()
    vm_stat = shutil.which("vm_stat")
    sysctl = shutil.which("sysctl")
    if not vm_stat or not sysctl:
        return _unknown_snapshot()
    try:
        vm = subprocess.check_output([vm_stat], text=True, timeout=2)
        swapouts_m = re.search(r"Swapouts:\s+(\d+)", vm)
        pages_m = re.search(r"Pages free:\s+(\d+)\.", vm)
        if not swapouts_m or not pages_m:
            return _unknown_snapshot()
        usage = subprocess.check_output(
            [sysctl, "-n", "vm.swapusage"], text=True, timeout=2
        )
        free_m = re.search(r"free = ([\d.]+)M", usage)
        if not free_m:
            return _unknown_snapshot()
        return ResourceSnapshot(
            swap_free_mib=float(free_m.group(1)),
            swapout_pages=int(swapouts_m.group(1)),
            pages_free=int(pages_m.group(1)),
            known=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError, ValueError):
        return _unknown_snapshot()


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

    Unknown / non-darwin snapshots never pause.
    """
    snapshot = snap or sample_resources()
    if not snapshot.known:
        return PauseDecision(False, "unknown_resources", snapshot)
    if snapshot.swap_free_mib < min_free_mib:
        return PauseDecision(True, "low_swap_free", snapshot)
    if snapshot.pages_free < min_pages_free:
        return PauseDecision(True, "low_pages_free", snapshot)
    return PauseDecision(False, None, snapshot)
