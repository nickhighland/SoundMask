from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import AppConfig, AppPaths
from app.db import init_db
from app.models import SoundMixLayer


def _make_db(temp_dir: str):
    paths = AppPaths(
        root=temp_dir,
        database=f"{temp_dir}/SoundMask.sqlite",
        sounds=f"{temp_dir}/sounds",
        tokens=f"{temp_dir}/tokens",
        logs=f"{temp_dir}/logs",
    )
    config = AppConfig(
        env="test",
        host="127.0.0.1",
        port=8080,
        session_secret="test-secret",
        google_client_secret=None,
        paths=paths,
    )
    for folder in (paths.root, paths.sounds, paths.tokens, paths.logs):
        Path(folder).mkdir(parents=True, exist_ok=True)
    return init_db(config), paths


def test_sound_mix_layers_fall_back_to_legacy_active_sound() -> None:
    with TemporaryDirectory() as temp_dir:
        db, paths = _make_db(temp_dir)
        sound_path = Path(paths.sounds) / "Rain.mp3"
        sound_path.write_bytes(b"demo")
        sound = db.add_sound("Rain.mp3", "Rain", str(sound_path), "audio/mpeg")
        db.set_active_sound(sound.id)

        layers = db.get_sound_mix_layers()

        assert len(layers) == 1
        assert layers[0].sound_id == sound.id
        assert layers[0].volume_percent == 100


def test_sound_mix_layers_store_explicit_per_layer_volume() -> None:
    with TemporaryDirectory() as temp_dir:
        db, paths = _make_db(temp_dir)
        rain_path = Path(paths.sounds) / "Rain.mp3"
        birds_path = Path(paths.sounds) / "Birds.mp3"
        rain_path.write_bytes(b"demo")
        birds_path.write_bytes(b"demo")
        rain = db.add_sound("Rain.mp3", "Rain", str(rain_path), "audio/mpeg")
        birds = db.add_sound("Birds.mp3", "Birds", str(birds_path), "audio/mpeg")

        db.set_sound_mix_layers(
            [
                SoundMixLayer(sound_id=rain.id, volume_percent=80),
                SoundMixLayer(sound_id=birds.id, volume_percent=35),
            ]
        )

        resolved = db.resolve_sound_mix_layers()

        assert [layer.sound.display_name for layer in resolved] == ["Rain", "Birds"]
        assert {layer.sound.id: layer.volume_percent for layer in resolved} == {
            rain.id: 80,
            birds.id: 35,
        }
