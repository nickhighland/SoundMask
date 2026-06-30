from __future__ import annotations

import os
import platform
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(slots=True)
class AppPaths:
    root: Path
    database: Path
    sounds: Path
    tokens: Path
    logs: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.database = Path(self.database)
        self.sounds = Path(self.sounds)
        self.tokens = Path(self.tokens)
        self.logs = Path(self.logs)


@dataclass(slots=True)
class AppConfig:
    env: str
    host: str
    port: int
    session_secret: str
    google_client_secret: str | None
    paths: AppPaths

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"


def _default_data_root() -> Path:
    explicit = os.getenv("SOUNDMASK_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser()
    if platform.system().lower() == "darwin":
        return Path.home() / ".SoundMask"
    return Path("/var/lib/soundmask")


def get_config() -> AppConfig:
    data_root = _default_data_root()
    paths = AppPaths(
        root=data_root,
        database=data_root / "SoundMask.sqlite",
        sounds=data_root / "sounds",
        tokens=data_root / "tokens",
        logs=data_root / "logs",
    )
    session_secret = os.getenv("SOUNDMASK_SESSION_SECRET")
    google_client_secret = os.getenv("SOUNDMASK_GOOGLE_CLIENT_SECRET")
    return AppConfig(
        env=os.getenv("SOUNDMASK_ENV", "development"),
        host=os.getenv("SOUNDMASK_HOST", "127.0.0.1"),
        port=int(os.getenv("SOUNDMASK_PORT", "8080")),
        session_secret=session_secret or secrets.token_urlsafe(32),
        google_client_secret=google_client_secret or None,
        paths=paths,
    )


def ensure_app_dirs(config: AppConfig) -> None:
    config.paths.root.mkdir(parents=True, exist_ok=True)
    config.paths.sounds.mkdir(parents=True, exist_ok=True)
    config.paths.tokens.mkdir(parents=True, exist_ok=True)
    config.paths.logs.mkdir(parents=True, exist_ok=True)
