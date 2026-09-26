import sys

from app.services.narrative_resources import sample_resources, should_pause_for_resources


def test_linux_without_sysctl_does_not_raise(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _name: None)
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
    decision = should_pause_for_resources()
    assert decision.should_pause is False
    assert decision.reason == "unknown_resources"
