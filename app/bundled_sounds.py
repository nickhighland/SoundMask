from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path

from app.config import AppConfig
from app.db import Database


def bundled_sounds_dir() -> Path:
    return Path(__file__).resolve().parent / "bundled_sounds"


def sync_bundled_sounds(config: AppConfig, db: Database) -> None:
    source_dir = bundled_sounds_dir()
    if not source_dir.exists():
        return

    for source_path in sorted(source_dir.glob("*")):
        if not source_path.is_file():
            continue
        target_path = config.paths.sounds / source_path.name
        if (
            not target_path.exists()
            or source_path.stat().st_size != target_path.stat().st_size
        ):
            shutil.copy2(source_path, target_path)

        display_name = source_path.stem.replace("_", " ")
        mime_type = mimetypes.guess_type(source_path.name)[0]
        db.add_sound(
            source_path.name,
            display_name,
            str(target_path),
            mime_type,
        )
