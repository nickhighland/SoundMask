from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import AppConfig
from app.display import format_datetime_label
from app.timezones import localize_datetime


@dataclass(frozen=True)
class LogSource:
    key: str
    label: str
    path: Path
    description: str


def available_sources(config: AppConfig) -> list[LogSource]:
    base = config.paths.logs
    return [
        LogSource(
            key="app",
            label="Application",
            path=base / "soundmask.log",
            description="Structured application events and errors.",
        ),
        LogSource(
            key="service",
            label="Service Output",
            path=base / "service.log",
            description="Web server stdout, stderr, and runtime diagnostics.",
        ),
        LogSource(
            key="updates",
            label="Updates",
            path=base / "updates.log",
            description="Automatic update checks and install activity.",
        ),
    ]


def default_source_key(config: AppConfig) -> str:
    for source in available_sources(config):
        if source.path.exists():
            return source.key
    return "app"


def _tail_lines(path: Path, lines: int) -> str:
    if not path.exists():
        return "No log file has been created for this source yet."
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not content:
        return "The log file exists, but it is currently empty."
    return "\n".join(content[-lines:])


def _log_timestamp_label(
    value: datetime,
    timezone_name: str | None,
) -> str | None:
    return format_datetime_label(localize_datetime(value, timezone_name))


def read_log_source(
    config: AppConfig,
    source_key: str,
    lines: int = 250,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    line_count = max(1, min(lines, 1000))
    selected = next(
        (source for source in available_sources(config) if source.key == source_key),
        None,
    )
    if selected is None:
        selected = next(
            source
            for source in available_sources(config)
            if source.key == default_source_key(config)
        )
    content = _tail_lines(selected.path, line_count)
    modified_at = None
    if selected.path.exists():
        modified_at = _log_timestamp_label(
            datetime.fromtimestamp(
                selected.path.stat().st_mtime,
                tz=timezone.utc,
            ),
            timezone_name,
        )
    return {
        "source": selected.key,
        "label": selected.label,
        "description": selected.description,
        "path": str(selected.path),
        "line_count": line_count,
        "modified_at": modified_at,
        "content": content,
        "updated_at": _log_timestamp_label(
            datetime.now(timezone.utc),
            timezone_name,
        ),
    }
