from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.models import ResolvedSoundMixLayer, SoundRecord
from app.sound_mixer import SoundMixManager


def _sound_record(sound_id: int, path: Path, name: str) -> SoundRecord:
    return SoundRecord(
        id=sound_id,
        filename=path.name,
        display_name=name,
        category=None,
        path=path,
        mime_type="audio/mpeg",
        created_at="2026-07-01T00:00:00+00:00",
        is_active=False,
    )


def test_single_full_volume_layer_falls_back_to_original_file_without_ffmpeg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        sound_path = Path(temp_dir) / "Rain.mp3"
        sound_path.write_bytes(b"demo")
        manager = SoundMixManager(Path(temp_dir) / "mixes")
        layers = [
            ResolvedSoundMixLayer(
                sound=_sound_record(1, sound_path, "Rain"),
                volume_percent=100,
            )
        ]

        monkeypatch.setattr("app.sound_mixer.shutil.which", lambda name: None)

        assert manager.playback_source(layers) == sound_path


def test_layered_mix_requires_ffmpeg_when_rendering_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        first_path = Path(temp_dir) / "Rain.mp3"
        second_path = Path(temp_dir) / "Birds.mp3"
        first_path.write_bytes(b"demo")
        second_path.write_bytes(b"demo")
        manager = SoundMixManager(Path(temp_dir) / "mixes")
        layers = [
            ResolvedSoundMixLayer(
                sound=_sound_record(1, first_path, "Rain"),
                volume_percent=100,
            ),
            ResolvedSoundMixLayer(
                sound=_sound_record(2, second_path, "Birds"),
                volume_percent=55,
            ),
        ]

        monkeypatch.setattr("app.sound_mixer.shutil.which", lambda name: None)

        with pytest.raises(RuntimeError, match="Install ffmpeg"):
            manager.playback_source(layers)


def test_playback_source_renders_normalized_file_when_ffmpeg_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        sound_path = Path(temp_dir) / "Rain.mp3"
        sound_path.write_bytes(b"demo")
        manager = SoundMixManager(Path(temp_dir) / "mixes")
        layers = [
            ResolvedSoundMixLayer(
                sound=_sound_record(1, sound_path, "Rain"),
                volume_percent=100,
            )
        ]
        captured: dict[str, object] = {}

        monkeypatch.setattr("app.sound_mixer.shutil.which", lambda name: "/usr/bin/ffmpeg")

        def fake_run(command, check):
            captured["command"] = command
            Path(command[-1]).write_bytes(b"rendered")

        monkeypatch.setattr("app.sound_mixer.subprocess.run", fake_run)

        output_path = manager.playback_source(layers)

        assert output_path is not None
        assert output_path.suffix == ".flac"
        assert output_path != sound_path
        assert "loudnorm=I=-18.0" in str(captured["command"])


def test_preview_source_renders_short_browser_mix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        rain_path = Path(temp_dir) / "Rain.mp3"
        birds_path = Path(temp_dir) / "Birds.mp3"
        rain_path.write_bytes(b"demo")
        birds_path.write_bytes(b"demo")
        manager = SoundMixManager(Path(temp_dir) / "mixes")
        layers = [
            ResolvedSoundMixLayer(
                sound=_sound_record(1, rain_path, "Rain"),
                volume_percent=100,
            ),
            ResolvedSoundMixLayer(
                sound=_sound_record(2, birds_path, "Birds"),
                volume_percent=45,
            ),
        ]
        captured: dict[str, object] = {}

        monkeypatch.setattr("app.sound_mixer.shutil.which", lambda name: "/usr/bin/ffmpeg")

        def fake_run(command, check):
            captured["command"] = command
            Path(command[-1]).write_bytes(b"preview")

        monkeypatch.setattr("app.sound_mixer.subprocess.run", fake_run)

        output_path = manager.preview_source(layers)

        assert output_path is not None
        assert output_path.suffix == ".wav"
        assert "-t" in captured["command"]
        assert "45" in captured["command"]
