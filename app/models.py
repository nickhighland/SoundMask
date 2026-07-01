from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class TriggerBlock:
    start_time: datetime
    end_time: datetime
    display_start_time: datetime | None = None
    display_end_time: datetime | None = None
    source: str = "calendar"
    is_all_day: bool = False
    calendar_id: str | None = None
    event_id_hash: str | None = None
    summary_hash: str | None = None
    matched_rule_id: int | None = None


@dataclass(slots=True)
class TitleMatchRule:
    id: int | None
    enabled: bool
    match_type: str
    match_text: str
    case_sensitive: bool = False
    trim_whitespace: bool = True
    ignore_cancelled: bool = True
    ignore_transparent: bool = True


@dataclass(slots=True)
class ManualState:
    manual_play_until: datetime | None = None
    mute_until: datetime | None = None


@dataclass(slots=True)
class SoundRecord:
    id: int
    filename: str
    display_name: str
    path: Path
    mime_type: str | None
    created_at: str
    is_active: bool


@dataclass(slots=True)
class SoundMixLayer:
    sound_id: int
    volume_percent: int


@dataclass(slots=True)
class ResolvedSoundMixLayer:
    sound: SoundRecord
    volume_percent: int


@dataclass(slots=True)
class CalendarAccount:
    id: int
    provider: str
    account_email: str | None
    token_path: str
    created_at: str
    updated_at: str
