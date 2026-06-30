from __future__ import annotations

from pathlib import Path
from threading import Thread

from app.audio import AudioManager


def test_audio_diagnostics_prefers_ffplay_when_mpv_missing(monkeypatch):
    available = {
        "mpv": None,
        "ffplay": "/usr/local/bin/ffplay",
        "afplay": "/usr/bin/afplay",
    }
    monkeypatch.setattr(
        "app.audio.shutil.which",
        lambda name: available.get(name),
    )

    manager = AudioManager(Path("/tmp/soundmask.sock"))
    diagnostics = manager.diagnostics()

    assert diagnostics["loop_backend"] == "ffplay"
    assert diagnostics["test_backend"] == "ffplay"
    assert diagnostics["mpv_available"] is False
    assert diagnostics["ffplay_available"] is True


def test_audio_test_reports_missing_backend(monkeypatch):
    monkeypatch.setattr("app.audio.shutil.which", lambda name: None)

    manager = AudioManager(Path("/tmp/soundmask.sock"))
    result = manager.test(Path("/tmp/example.mp3"), 35)

    assert result["ok"] is False
    assert "No supported audio backend" in str(result["message"])


def test_audio_start_returns_without_deadlocking_when_no_backend(monkeypatch):
    monkeypatch.setattr("app.audio.shutil.which", lambda name: None)

    manager = AudioManager(Path("/tmp/soundmask.sock"))
    worker = Thread(target=manager.start, args=(Path("/tmp/example.mp3"), 35))
    worker.start()
    worker.join(timeout=1)

    assert worker.is_alive() is False
