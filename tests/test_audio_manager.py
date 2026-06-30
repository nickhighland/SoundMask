from __future__ import annotations

from pathlib import Path
from threading import Thread
from unittest.mock import Mock

from app.audio import AudioManager, MAX_MPV_VOLUME_PERCENT, MAX_STANDARD_VOLUME_PERCENT


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

    def fake_launch(self, command, backend, sound_path, volume_percent, env=None):
        captured["command"] = command
        captured["backend"] = backend
        captured["volume_percent"] = volume_percent
        captured["env"] = env
        return False

    monkeypatch.setattr(AudioManager, "_launch_process", fake_launch)

    manager = AudioManager(Path("/tmp/soundmask.sock"))
    manager.start(Path("/tmp/example.mp3"), 35)

    assert captured["backend"] == "mpv"
    assert "--ao=alsa" in captured["command"]
    assert f"--volume-max={MAX_MPV_VOLUME_PERCENT}" in captured["command"]
    assert captured["volume_percent"] == 35
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


def test_audio_test_clamps_ffplay_volume_to_supported_max(monkeypatch):
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
        return FakeProcess()

    monkeypatch.setattr("app.audio.subprocess.Popen", fake_popen)

    manager = AudioManager(Path("/tmp/soundmask.sock"))
    result = manager.test(Path("/tmp/example.mp3"), 150)

    assert result["ok"] is True
    assert str(MAX_STANDARD_VOLUME_PERCENT) in captured["command"]


def test_audio_set_volume_clamps_mpv_gain_to_boost_limit(monkeypatch):
    captured: dict[str, object] = {}

    def fake_send(self, payload):
        captured["payload"] = payload

    monkeypatch.setattr(AudioManager, "_send_command", fake_send)
    manager = AudioManager(Path("/tmp/soundmask.sock"))
    manager._backend = "mpv"
    manager._process = Mock()
    manager._process.poll.return_value = None

    manager.set_volume(200)

    assert captured["payload"] == {
        "command": ["set_property", "volume", MAX_MPV_VOLUME_PERCENT]
    }


def test_audio_start_ignores_mpv_control_race_during_fade_in(monkeypatch):
    monkeypatch.setattr("app.audio.platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "app.audio.shutil.which",
        lambda name: "/usr/bin/mpv" if name == "mpv" else None,
    )

    def fake_launch(self, command, backend, sound_path, volume_percent, env=None):
        self._backend = backend
        self._current_sound = sound_path
        self._current_volume_percent = volume_percent
        self._process = Mock()
        self._process.poll.return_value = None
        return True

    monkeypatch.setattr(AudioManager, "_launch_process", fake_launch)
    monkeypatch.setattr(
        AudioManager,
        "_send_command",
        lambda self, payload: (_ for _ in ()).throw(FileNotFoundError("socket not ready")),
    )

    manager = AudioManager(Path("/tmp/soundmask.sock"))
    manager.fade_in_seconds = 1
    manager.start(Path("/tmp/example.mp3"), 35)

    assert manager._backend == "mpv"


def test_audio_set_volume_ignores_mpv_control_race(monkeypatch):
    monkeypatch.setattr(
        AudioManager,
        "_send_command",
        lambda self, payload: (_ for _ in ()).throw(FileNotFoundError("socket not ready")),
    )
    manager = AudioManager(Path("/tmp/soundmask.sock"))
    manager._backend = "mpv"
    manager._process = Mock()
    manager._process.poll.return_value = None

    manager.set_volume(35)

    assert manager.is_playing() is True
