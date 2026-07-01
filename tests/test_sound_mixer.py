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


def test_single_full_volume_layer_uses_original_file() -> None:
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
