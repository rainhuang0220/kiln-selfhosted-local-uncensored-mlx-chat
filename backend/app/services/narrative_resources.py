"""Memory / swap pressure sampling for narrative scheduling.

Does not restart or kill MLX. Pausing only blocks scheduling the next segment.

Probe order (never raises FileNotFoundError):
  1. ``shutil.which("sysctl")``
  2. absolute ``/usr/sbin/sysctl`` (then ``/sbin/sysctl``)
  3. Linux ``/proc/meminfo``
  4. Darwin ``vm_stat`` (+ resolved sysctl for ``vm.swapusage``)

Unknown / unreadable samples return ``known=False`` → ``should_pause=False``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_SYSCTL_FALLBACKS = ("/usr/sbin/sysctl", "/sbin/sysctl")
_VM_STAT_FALLBACKS = ("/usr/bin/vm_stat", "/usr/sbin/vm_stat")
_MEMINFO_PATH = Path("/proc/meminfo")


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


def _executable(path: str) -> str | None:
    try:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    except OSError:
        return None
    return None


def _resolve_sysctl() -> str | None:
    """which → /usr/sbin/sysctl → /sbin/sysctl."""
    found = shutil.which("sysctl")
    if found:
        return found
    for candidate in _SYSCTL_FALLBACKS:
        resolved = _executable(candidate)
        if resolved:
            return resolved
    return None


def _resolve_vm_stat() -> str | None:
    found = shutil.which("vm_stat")
    if found:
        return found
    for candidate in _VM_STAT_FALLBACKS:
        resolved = _executable(candidate)
        if resolved:
            return resolved
    return None


def _sample_linux_meminfo() -> ResourceSnapshot | None:
    """Parse /proc/meminfo. Returns None when unreadable or incomplete."""
    try:
        text = _MEMINFO_PATH.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeError):
        return None
    fields: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[0].rstrip(":")
        try:
            fields[key] = int(parts[1])
        except ValueError:
            continue
    # Values are kB.
    swap_free_kb = fields.get("SwapFree")
    mem_avail_kb = fields.get("MemAvailable")
    if mem_avail_kb is None:
        mem_avail_kb = fields.get("MemFree")
    if swap_free_kb is None or mem_avail_kb is None:
        return None
    page_kb = 4  # typical; pages_free is comparative only
    return ResourceSnapshot(
        swap_free_mib=swap_free_kb / 1024.0,
        swapout_pages=0,
        pages_free=max(0, mem_avail_kb // page_kb),
        known=True,
    )


def _sample_darwin(sysctl: str, vm_stat: str) -> ResourceSnapshot | None:
    try:
        vm = subprocess.check_output([vm_stat], text=True, timeout=2)
        swapouts_m = re.search(r"Swapouts:\s+(\d+)", vm)
        pages_m = re.search(r"Pages free:\s+(\d+)\.", vm)
        if not swapouts_m or not pages_m:
            return None
        usage = subprocess.check_output(
            [sysctl, "-n", "vm.swapusage"], text=True, timeout=2
        )
        free_m = re.search(r"free = ([\d.]+)M", usage)
        if not free_m:
            return None
        return ResourceSnapshot(
            swap_free_mib=float(free_m.group(1)),
            swapout_pages=int(swapouts_m.group(1)),
            pages_free=int(pages_m.group(1)),
            known=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError, ValueError):
        return None


def sample_resources() -> ResourceSnapshot:
    """Sample swap/RAM. Never raises FileNotFoundError on missing tools."""
    try:
        sysctl = _resolve_sysctl()
        if sys.platform.startswith("linux"):
            mem = _sample_linux_meminfo()
            if mem is not None:
                return mem
            return _unknown_snapshot()

        if sys.platform != "darwin":
            return _unknown_snapshot()

        vm_stat = _resolve_vm_stat()
        if not sysctl or not vm_stat:
            return _unknown_snapshot()
        snap = _sample_darwin(sysctl, vm_stat)
        return snap if snap is not None else _unknown_snapshot()
    except (FileNotFoundError, OSError, ValueError):
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
