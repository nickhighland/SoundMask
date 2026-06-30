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


def test_audio_launch_error_collapses_missing_linux_audio_device_noise(monkeypatch):
    monkeypatch.setattr("app.audio.platform.system", lambda: "Linux")
    manager = AudioManager(Path("/tmp/soundmask.sock"))

    message = manager._launch_error_message(
        "mpv",
        "\n".join(
            [
                "ALSA lib confmisc.c:855:(parse_card) cannot find card '0'",
                "ALSA lib pcm.c:2722:(snd_pcm_open_noupdate) Unknown PCM default",
                "couldn't open play stream: No such file or directory",
            ]
        ),
    )

    assert "No Linux audio output device is available" in message


def test_audio_diagnostics_include_device_hint():
    manager = AudioManager(Path("/tmp/soundmask.sock"))

    diagnostics = manager.diagnostics()

    assert diagnostics["audio_device_hint"] is not None


def test_audio_start_uses_alsa_output_with_mpv_on_linux(monkeypatch):
    monkeypatch.setattr("app.audio.platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "app.audio.shutil.which",
        lambda name: "/usr/bin/mpv" if name == "mpv" else None,
    )
    captured: dict[str, object] = {}

    def fake_launch(self, command, backend, sound_path, env=None):
        captured["command"] = command
        captured["backend"] = backend
        captured["env"] = env
        return False

    monkeypatch.setattr(AudioManager, "_launch_process", fake_launch)

    manager = AudioManager(Path("/tmp/soundmask.sock"))
    manager.start(Path("/tmp/example.mp3"), 35)

    assert captured["backend"] == "mpv"
    assert "--ao=alsa" in captured["command"]
    assert captured["env"] is None


def test_audio_test_uses_alsa_sdl_driver_with_ffplay_on_linux(monkeypatch):
    monkeypatch.setattr("app.audio.platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "app.audio.shutil.which",
        lambda name: "/usr/bin/ffplay" if name == "ffplay" else None,
    )
    captured: dict[str, object] = {}

    class FakeProcess:
        def poll(self):
            return None

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs.get("env")
        return FakeProcess()

    monkeypatch.setattr("app.audio.subprocess.Popen", fake_popen)

    manager = AudioManager(Path("/tmp/soundmask.sock"))
    result = manager.test(Path("/tmp/example.mp3"), 35)

    assert result["ok"] is True
    assert captured["env"]["SDL_AUDIODRIVER"] == "alsa"
