from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import AppConfig, AppPaths
from app.db import init_db
from app.models import SoundMixLayer, SoundRecord
from app.sound_categories import (
    available_sound_categories,
    group_sounds_by_category,
    normalize_sound_category_name,
)


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


def test_sound_records_store_categories() -> None:
    with TemporaryDirectory() as temp_dir:
        db, paths = _make_db(temp_dir)
        sound_path = Path(paths.sounds) / "Busy Highway.mp3"
        sound_path.write_bytes(b"demo")

        sound = db.add_sound(
            "Busy Highway.mp3",
            "Busy Highway",
            str(sound_path),
            "audio/mpeg",
            category="Transportation",
        )

        assert sound.category == "Transportation"
        assert db.get_sound(sound.id).category == "Transportation"


def test_sound_library_groups_bundled_sounds_by_category_and_uses_stored_upload_categories() -> None:
    sounds = [
        SoundRecord(
            id=1,
            filename="White Noise.mp3",
            display_name="White Noise",
            category=None,
            path=Path("/tmp/White Noise.mp3"),
            mime_type="audio/mpeg",
            created_at="",
            is_active=False,
        ),
        SoundRecord(
            id=2,
            filename="Birds.mp3",
            display_name="Birds",
            category=None,
            path=Path("/tmp/Birds.mp3"),
            mime_type="audio/mpeg",
            created_at="",
            is_active=False,
        ),
        SoundRecord(
            id=3,
            filename="Rain.mp3",
            display_name="Rain",
            category=None,
            path=Path("/tmp/Rain.mp3"),
            mime_type="audio/mpeg",
            created_at="",
            is_active=False,
        ),
        SoundRecord(
            id=4,
            filename="Wind.mp3",
            display_name="Wind",
            category=None,
            path=Path("/tmp/Wind.mp3"),
            mime_type="audio/mpeg",
            created_at="",
            is_active=False,
        ),
        SoundRecord(
            id=5,
            filename="Busy Highway.mp3",
            display_name="Busy Highway",
            category=None,
            path=Path("/tmp/Busy Highway.mp3"),
            mime_type="audio/mpeg",
            created_at="",
            is_active=False,
        ),
        SoundRecord(
            id=6,
            filename="Train Passing.mp3",
            display_name="Train Passing",
            category=None,
            path=Path("/tmp/Train Passing.mp3"),
            mime_type="audio/mpeg",
            created_at="",
            is_active=False,
        ),
        SoundRecord(
            id=7,
            filename="Custom Loop.mp3",
            display_name="Custom Loop",
            category="Office Ambience",
            path=Path("/tmp/Custom Loop.mp3"),
            mime_type="audio/mpeg",
            created_at="",
            is_active=False,
        ),
    ]

    grouped = group_sounds_by_category(
        sounds,
        {
            "White Noise.mp3",
            "Birds.mp3",
            "Rain.mp3",
            "Wind.mp3",
            "Busy Highway.mp3",
            "Train Passing.mp3",
        },
    )

    assert [label for label, _items in grouped] == [
        "Noise",
        "Nature",
        "Water",
        "Weather",
        "Transportation",
        "Office Ambience",
    ]
    assert [sound.display_name for sound in grouped[0][1]] == ["White Noise"]
    assert [sound.display_name for sound in grouped[3][1]] == ["Wind"]
    assert [sound.display_name for sound in grouped[4][1]] == [
        "Busy Highway",
        "Train Passing",
    ]
    assert [sound.display_name for sound in grouped[-1][1]] == ["Custom Loop"]


def test_available_sound_categories_include_standard_and_custom_names() -> None:
    sounds = [
        SoundRecord(
            id=1,
            filename="Custom Loop.mp3",
            display_name="Custom Loop",
            category="Office Ambience",
            path=Path("/tmp/Custom Loop.mp3"),
            mime_type="audio/mpeg",
            created_at="",
            is_active=False,
        )
    ]

    categories = available_sound_categories(sounds, set())

    assert categories[:6] == [
        "Noise",
        "Nature",
        "Water",
        "Weather",
        "Transportation",
        "City & Indoor",
    ]
    assert "Custom Uploads" in categories
    assert "Office Ambience" in categories


def test_normalize_sound_category_name_maps_legacy_transport_label() -> None:
    assert normalize_sound_category_name("Travel & Transit") == "Transportation"


def test_sound_presets_round_trip_and_replace_matching_names() -> None:
    with TemporaryDirectory() as temp_dir:
        db, paths = _make_db(temp_dir)
        rain_path = Path(paths.sounds) / "Rain.mp3"
        birds_path = Path(paths.sounds) / "Birds.mp3"
        rain_path.write_bytes(b"demo")
        birds_path.write_bytes(b"demo")
        rain = db.add_sound("Rain.mp3", "Rain", str(rain_path), "audio/mpeg")
        birds = db.add_sound("Birds.mp3", "Birds", str(birds_path), "audio/mpeg")

        original = db.save_sound_preset(
            "Rain + Birds",
            [
                SoundMixLayer(sound_id=rain.id, volume_percent=100),
                SoundMixLayer(sound_id=birds.id, volume_percent=45),
            ],
        )
        updated = db.save_sound_preset(
            "rain + birds",
            [SoundMixLayer(sound_id=birds.id, volume_percent=60)],
        )

        presets = db.list_sound_presets()

        assert len(presets) == 1
        assert presets[0].id == original.id == updated.id
        assert presets[0].name == "rain + birds"
        assert [(layer.sound_id, layer.volume_percent) for layer in presets[0].layers] == [
            (birds.id, 60),
        ]
