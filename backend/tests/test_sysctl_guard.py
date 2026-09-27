import os
import sys
from pathlib import Path

from app.services.narrative_resources import (
    sample_resources,
    should_pause_for_resources,
)


def test_linux_without_sysctl_does_not_raise(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    # No /proc/meminfo either → unknown, do not pause.
    monkeypatch.setattr(
        "app.services.narrative_resources._MEMINFO_PATH",
        Path("/nonexistent/meminfo"),
    )
    snap = sample_resources()
    assert snap.known is False
    decision = should_pause_for_resources(snap)
    assert decision.should_pause is False
    # also via live sample path
    decision2 = should_pause_for_resources()
    assert decision2.should_pause is False


def test_darwin_missing_binaries_safe(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        "app.services.narrative_resources._executable", lambda _path: None
    )
    decision = should_pause_for_resources()
    assert decision.should_pause is False
    assert decision.reason == "unknown_resources"


def test_darwin_which_miss_falls_back_to_usr_sbin(monkeypatch, tmp_path):
    """PATH without /usr/sbin must not raise; absolute fallback is used."""
    monkeypatch.setattr(sys, "platform", "darwin")
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _name: None)

    fake_sysctl = tmp_path / "sysctl"
    fake_vm = tmp_path / "vm_stat"
    fake_sysctl.write_text("#!/bin/sh\necho 'free = 1024.00M used = 0.00M'\n")
    fake_vm.write_text(
        "#!/bin/sh\n"
        "echo 'Pages free:     50000.'\n"
        "echo 'Swapouts:                 12.'\n"
    )
    os.chmod(fake_sysctl, 0o755)
    os.chmod(fake_vm, 0o755)

    def fake_executable(path: str) -> str | None:
        if path.endswith("sysctl"):
            return str(fake_sysctl)
        if path.endswith("vm_stat"):
            return str(fake_vm)
        return None

    monkeypatch.setattr(
        "app.services.narrative_resources._executable", fake_executable
    )

    # check_output still needs to run our fakes with the resolved paths.
    import subprocess

    real_check = subprocess.check_output

    def check_output(args, **kwargs):
        # Map absolute-looking fallbacks to our temp binaries via fake_executable.
        cmd = list(args)
        if cmd and str(cmd[0]).endswith("sysctl"):
            cmd[0] = str(fake_sysctl)
        elif cmd and str(cmd[0]).endswith("vm_stat"):
            cmd[0] = str(fake_vm)
        # /bin/sh spawn under a loaded full suite can exceed the 2 s production timeout.
        kwargs.pop("timeout", None)
        return real_check(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "check_output", check_output)

    snap = sample_resources()
    assert snap.known is True
    assert snap.swap_free_mib == 1024.0
    assert snap.pages_free == 50000
    assert snap.swapout_pages == 12
    decision = should_pause_for_resources(snap)
    assert decision.should_pause is False


def test_linux_meminfo_known_when_readable(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:       16384000 kB\n"
        "MemFree:         4096000 kB\n"
        "MemAvailable:    8192000 kB\n"
        "SwapFree:         512000 kB\n"
    )
    monkeypatch.setattr(
        "app.services.narrative_resources._MEMINFO_PATH", meminfo
    )
    snap = sample_resources()
    assert snap.known is True
    assert abs(snap.swap_free_mib - 500.0) < 0.01
    assert snap.pages_free == 8192000 // 4
    decision = should_pause_for_resources(snap, min_free_mib=256.0)
    assert decision.should_pause is False


def test_sample_resources_never_raises_filenotfound(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    import shutil
    import subprocess

    monkeypatch.setattr(shutil, "which", lambda _name: "/missing/sysctl")
    monkeypatch.setattr(
        "app.services.narrative_resources._executable",
        lambda path: path,  # pretend absolute paths exist
    )
    monkeypatch.setattr(
        "app.services.narrative_resources._resolve_vm_stat",
        lambda: "/missing/vm_stat",
    )

    def boom(*_a, **_k):
        raise FileNotFoundError(2, "No such file or directory", "sysctl")

    monkeypatch.setattr(subprocess, "check_output", boom)
    snap = sample_resources()
    assert snap.known is False
    assert should_pause_for_resources(snap).should_pause is False
