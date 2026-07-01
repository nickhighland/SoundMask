from __future__ import annotations

from collections.abc import Iterable

from app.models import SoundRecord

DEFAULT_UPLOAD_CATEGORY = "Custom Uploads"
FALLBACK_LIBRARY_CATEGORY = "Library"
SOUND_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Noise", ("white noise", "brown noise", "pink noise", "noise")),
    ("Nature", ("birds", "insects", "serengeti", "campfire")),
    ("Water", ("rain", "stream", "waterfall", "waves", "river", "creek")),
    ("Weather", ("wind farm", "wind", "thunderstorm", "storm")),
    ("Transportation", ("train", "highway", "traffic", "transit")),
    (
        "City & Indoor",
        (
            "city square",
            "crowded cafeteria",
            "restaurant ambience",
            "time square",
            "typing",
        ),
    ),
)
SOUND_CATEGORY_ORDER: tuple[str, ...] = (
    *(label for label, _keywords in SOUND_CATEGORY_RULES),
    DEFAULT_UPLOAD_CATEGORY,
    FALLBACK_LIBRARY_CATEGORY,
)


def normalize_sound_category_name(raw_value: str | None) -> str | None:
    text = " ".join((raw_value or "").strip().split())
    return text or None


def infer_bundled_sound_category(display_name: str) -> str:
    normalized_name = display_name.lower()
    for label, keywords in SOUND_CATEGORY_RULES:
        if any(keyword in normalized_name for keyword in keywords):
            return label
    return FALLBACK_LIBRARY_CATEGORY


def effective_sound_category(
    sound: SoundRecord,
    bundled_filenames: set[str],
) -> str:
    if sound.category:
        return sound.category
    if sound.filename in bundled_filenames:
        return infer_bundled_sound_category(sound.display_name)
    return DEFAULT_UPLOAD_CATEGORY


def sound_category_sort_key(category_name: str) -> tuple[int, str]:
    try:
        return (SOUND_CATEGORY_ORDER.index(category_name), category_name.lower())
    except ValueError:
        return (len(SOUND_CATEGORY_ORDER), category_name.lower())


def available_sound_categories(
    sounds: Iterable[SoundRecord],
    bundled_filenames: set[str],
) -> list[str]:
    categories = {
        label
        for label, _keywords in SOUND_CATEGORY_RULES
    }
    categories.add(DEFAULT_UPLOAD_CATEGORY)
    categories.update(
        effective_sound_category(sound, bundled_filenames)
        for sound in sounds
    )
    return sorted(categories, key=sound_category_sort_key)


def group_sounds_by_category(
    sounds: list[SoundRecord],
    bundled_filenames: set[str],
) -> list[tuple[str, list[SoundRecord]]]:
    grouped: dict[str, list[SoundRecord]] = {}
    for sound in sounds:
        grouped.setdefault(
            effective_sound_category(sound, bundled_filenames),
            [],
        ).append(sound)
    return sorted(grouped.items(), key=lambda item: sound_category_sort_key(item[0]))
