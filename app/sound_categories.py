from __future__ import annotations

from collections.abc import Iterable
import re

from app.models import SoundRecord

DEFAULT_UPLOAD_CATEGORY = "Custom Uploads"
FALLBACK_LIBRARY_CATEGORY = "Library"
LEGACY_SOUND_CATEGORY_ALIASES: dict[str, str] = {
    "travel & transit": "Transportation",
}
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
    if not text:
        return None
    return LEGACY_SOUND_CATEGORY_ALIASES.get(text.casefold(), text)


def _sound_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _keyword_matches_name(name_tokens: list[str], keyword: str) -> bool:
    keyword_tokens = _sound_tokens(keyword)
    if not keyword_tokens:
        return False
    if len(keyword_tokens) == 1:
        return keyword_tokens[0] in name_tokens
    window_size = len(keyword_tokens)
    return any(
        name_tokens[index:index + window_size] == keyword_tokens
        for index in range(len(name_tokens) - window_size + 1)
    )


def infer_bundled_sound_category(display_name: str) -> str:
    name_tokens = _sound_tokens(display_name)
    for label, keywords in SOUND_CATEGORY_RULES:
        if any(_keyword_matches_name(name_tokens, keyword) for keyword in keywords):
            return label
    return FALLBACK_LIBRARY_CATEGORY


def effective_sound_category(
    sound: SoundRecord,
    bundled_filenames: set[str],
) -> str:
    normalized_category = normalize_sound_category_name(sound.category)
    if normalized_category:
        return normalized_category
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
