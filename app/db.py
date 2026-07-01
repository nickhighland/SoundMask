from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from app.config import AppConfig
from app.models import (
    CalendarAccount,
    ResolvedSoundMixLayer,
    SoundMixLayer,
    SoundPreset,
    SoundRecord,
    TitleMatchRule,
    TriggerBlock,
)
from app.audio import DEFAULT_VOLUME_PERCENT
from app.timezones import SYSTEM_TIMEZONE


DEFAULT_SETTINGS: dict[str, Any] = {
    "trigger_mode": "fake",
    "calendar_source": "google",
    "calendar_sync_interval_seconds": 60,
    "start_buffer_minutes": 2,
    "end_buffer_minutes": 3,
    "ignore_all_day_events": True,
    "max_event_duration_minutes": 240,
    "active_hours_enabled": True,
    "active_hours_start": "07:00",
    "active_hours_end": "21:00",
    "timezone_name": SYSTEM_TIMEZONE,
    "volume_percent": DEFAULT_VOLUME_PERCENT,
    "audio_output_device": "auto",
    "fade_in_seconds": 2,
    "fade_out_seconds": 3,
    "manual_play_duration_minutes": 60,
    "debug_store_event_summaries": False,
}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    category TEXT,
                    path TEXT NOT NULL,
                    mime_type TEXT,
                    created_at TEXT NOT NULL,
                    is_active INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS calendar_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    account_email TEXT,
                    token_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS calendars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    calendar_id TEXT NOT NULL UNIQUE,
                    display_name TEXT,
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS title_match_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    enabled INTEGER DEFAULT 1,
                    match_type TEXT NOT NULL,
                    match_text TEXT NOT NULL,
                    case_sensitive INTEGER DEFAULT 0,
                    trim_whitespace INTEGER DEFAULT 1,
                    ignore_cancelled INTEGER DEFAULT 1,
                    ignore_transparent INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trigger_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    calendar_id TEXT,
                    event_id_hash TEXT,
                    summary_hash TEXT,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    buffered_start_time TEXT NOT NULL,
                    buffered_end_time TEXT NOT NULL,
                    matched_rule_id INTEGER,
                    created_at TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._migrate_schema(conn)
        self.seed_defaults()

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        sound_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(sounds)").fetchall()
        }
        if sound_columns and "category" not in sound_columns:
            conn.execute("ALTER TABLE sounds ADD COLUMN category TEXT")
        if sound_columns:
            conn.execute(
                """
                UPDATE sounds
                SET category = 'Transportation'
                WHERE LOWER(TRIM(category)) = 'travel & transit'
                """
            )

        trigger_cache_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(trigger_cache)").fetchall()
        }
        if not trigger_cache_columns:
            return
        if "buffered_start_time" not in trigger_cache_columns:
            conn.execute(
                "ALTER TABLE trigger_cache ADD COLUMN buffered_start_time TEXT"
            )
        if "buffered_end_time" not in trigger_cache_columns:
            conn.execute(
                "ALTER TABLE trigger_cache ADD COLUMN buffered_end_time TEXT"
            )
        conn.execute(
            """
            UPDATE trigger_cache
            SET buffered_start_time = COALESCE(buffered_start_time, start_time),
                buffered_end_time = COALESCE(buffered_end_time, end_time)
            WHERE buffered_start_time IS NULL OR buffered_end_time IS NULL
            """
        )

    def seed_defaults(self) -> None:
        now = utcnow_iso()
        with self.connect() as conn:
            for key, value in DEFAULT_SETTINGS.items():
                conn.execute(
                    """
                    INSERT INTO settings(key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO NOTHING
                    """,
                    (key, self._encode(value), now),
                )
            conn.execute(
                """
                INSERT INTO title_match_rules(
                    enabled, match_type, match_text, case_sensitive,
                    trim_whitespace, ignore_cancelled, ignore_transparent,
                    created_at, updated_at
                )
                SELECT 1, 'exact', 'Counseling appointment', 0, 1, 1, 1, ?, ?
                WHERE NOT EXISTS (SELECT 1 FROM title_match_rules)
                """,
                (now, now),
            )
            conn.execute(
                """
                INSERT INTO app_state(key, value, updated_at)
                VALUES ('fake_blocks', '[]', ?)
                ON CONFLICT(key) DO NOTHING
                """,
                (now,),
            )
            conn.execute(
                """
                INSERT INTO app_state(key, value, updated_at)
                VALUES ('ics_feeds', '[]', ?)
                ON CONFLICT(key) DO NOTHING
                """,
                (now,),
            )

    def _encode(self, value: Any) -> str:
        return json.dumps(value)

    def _decode(self, value: str) -> Any:
        return json.loads(value)

    def get_settings(self) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: self._decode(row["value"]) for row in rows}

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return self._decode(row["value"]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, self._encode(value), utcnow_iso()),
            )

    def get_state(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_state WHERE key = ?",
                (key,),
            ).fetchone()
        return self._decode(row["value"]) if row else default

    def set_state(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_state(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, self._encode(value), utcnow_iso()),
            )

    def list_sounds(self) -> list[SoundRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sounds ORDER BY LOWER(display_name) ASC, created_at ASC"
            ).fetchall()
        return [
            SoundRecord(
                id=row["id"],
                filename=row["filename"],
                display_name=row["display_name"],
                category=row["category"],
                path=Path(row["path"]),
                mime_type=row["mime_type"],
                created_at=row["created_at"],
                is_active=bool(row["is_active"]),
            )
            for row in rows
        ]

    def get_sound_by_filename(self, filename: str) -> SoundRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sounds WHERE filename = ? ORDER BY id DESC LIMIT 1",
                (filename,),
            ).fetchone()
        if row is None:
            return None
        return SoundRecord(
            id=row["id"],
            filename=row["filename"],
            display_name=row["display_name"],
            category=row["category"],
            path=Path(row["path"]),
            mime_type=row["mime_type"],
            created_at=row["created_at"],
            is_active=bool(row["is_active"]),
        )

    def get_sound(self, sound_id: int) -> SoundRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sounds WHERE id = ?",
                (sound_id,),
            ).fetchone()
        if row is None:
            return None
        return SoundRecord(
            id=row["id"],
            filename=row["filename"],
            display_name=row["display_name"],
            category=row["category"],
            path=Path(row["path"]),
            mime_type=row["mime_type"],
            created_at=row["created_at"],
            is_active=bool(row["is_active"]),
        )

    def get_active_sound(self) -> SoundRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sounds WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return SoundRecord(
            id=row["id"],
            filename=row["filename"],
            display_name=row["display_name"],
            category=row["category"],
            path=Path(row["path"]),
            mime_type=row["mime_type"],
            created_at=row["created_at"],
            is_active=True,
        )

    def add_sound(
        self,
        filename: str,
        display_name: str,
        path: str,
        mime_type: str | None,
        category: str | None = None,
    ) -> SoundRecord:
        existing = self.get_sound_by_filename(filename)
        if existing is not None:
            with self.connect() as conn:
                if category is None:
                    conn.execute(
                        """
                        UPDATE sounds
                        SET display_name = ?, path = ?, mime_type = ?
                        WHERE id = ?
                        """,
                        (display_name, path, mime_type, existing.id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE sounds
                        SET display_name = ?, category = ?, path = ?, mime_type = ?
                        WHERE id = ?
                        """,
                        (display_name, category, path, mime_type, existing.id),
                    )
            return self.get_sound(existing.id) or existing
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sounds(filename, display_name, category, path, mime_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (filename, display_name, category, path, mime_type, utcnow_iso()),
            )
            sound_id = int(cursor.lastrowid)
        sound = self.get_sound(sound_id)
        if sound is None:
            raise RuntimeError("Sound record could not be loaded after insert.")
        return sound

    def set_active_sound(self, sound_id: int) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE sounds SET is_active = 0")
            conn.execute(
                "UPDATE sounds SET is_active = 1 WHERE id = ?",
                (sound_id,),
            )

    def delete_sound(self, sound_id: int) -> SoundRecord | None:
        sound = self.get_sound(sound_id)
        if sound is None:
            return None
        with self.connect() as conn:
            conn.execute("DELETE FROM sounds WHERE id = ?", (sound_id,))
        return sound

    def get_sound_mix_layers(self) -> list[SoundMixLayer]:
        payload = self.get_state("sound_mix_layers", None)
        if payload is None:
            active_sound = self.get_active_sound()
            if active_sound is None:
                return []
            return [SoundMixLayer(sound_id=active_sound.id, volume_percent=100)]
        layers: list[SoundMixLayer] = []
        for item in payload:
            try:
                sound_id = int(item.get("sound_id"))
                volume_percent = max(0, min(int(item.get("volume_percent", 100)), 100))
            except (TypeError, ValueError, AttributeError):
                continue
            layers.append(
                SoundMixLayer(
                    sound_id=sound_id,
                    volume_percent=volume_percent,
                )
            )
        return layers

    def resolve_sound_mix_layers(self) -> list[ResolvedSoundMixLayer]:
        sounds_by_id = {sound.id: sound for sound in self.list_sounds()}
        resolved_layers: list[ResolvedSoundMixLayer] = []
        for layer in self.get_sound_mix_layers():
            sound = sounds_by_id.get(layer.sound_id)
            if sound is None:
                continue
            resolved_layers.append(
                ResolvedSoundMixLayer(
                    sound=sound,
                    volume_percent=layer.volume_percent,
                )
            )
        return resolved_layers

    def set_sound_mix_layers(self, layers: list[SoundMixLayer]) -> None:
        payload = [
            {
                "sound_id": int(layer.sound_id),
                "volume_percent": max(0, min(int(layer.volume_percent), 100)),
            }
            for layer in layers
        ]
        self.set_state("sound_mix_layers", payload)

    def remove_sound_from_mix(self, sound_id: int) -> None:
        remaining_layers = [
            layer
            for layer in self.get_sound_mix_layers()
            if layer.sound_id != sound_id
        ]
        self.set_sound_mix_layers(remaining_layers)

    def list_sound_presets(self) -> list[SoundPreset]:
        payload = self.get_state("sound_presets", [])
        presets: list[SoundPreset] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            preset_id = str(item.get("id") or "").strip()
            preset_name = str(item.get("name") or "").strip()
            created_at = str(item.get("created_at") or "").strip()
            updated_at = str(item.get("updated_at") or "").strip()
            if not preset_id or not preset_name:
                continue
            layers: list[SoundMixLayer] = []
            for raw_layer in item.get("layers", []):
                try:
                    sound_id = int(raw_layer.get("sound_id"))
                    volume_percent = max(
                        0,
                        min(int(raw_layer.get("volume_percent", 100)), 100),
                    )
                except (TypeError, ValueError, AttributeError):
                    continue
                layers.append(
                    SoundMixLayer(
                        sound_id=sound_id,
                        volume_percent=volume_percent,
                    )
                )
            presets.append(
                SoundPreset(
                    id=preset_id,
                    name=preset_name,
                    layers=layers,
                    created_at=created_at or utcnow_iso(),
                    updated_at=updated_at or created_at or utcnow_iso(),
                )
            )
        return sorted(presets, key=lambda preset: preset.name.casefold())

    def get_sound_preset(self, preset_id: str) -> SoundPreset | None:
        for preset in self.list_sound_presets():
            if preset.id == preset_id:
                return preset
        return None

    def save_sound_preset(
        self,
        name: str,
        layers: list[SoundMixLayer],
    ) -> SoundPreset:
        normalized_name = " ".join(name.strip().split())
        if not normalized_name:
            raise ValueError("Preset name is required.")
        if not layers:
            raise ValueError("Select at least one sound layer first.")

        now = utcnow_iso()
        presets = self.list_sound_presets()
        updated_preset: SoundPreset | None = None
        updated_payload: list[dict[str, Any]] = []
        for preset in presets:
            if preset.name.casefold() == normalized_name.casefold():
                updated_preset = SoundPreset(
                    id=preset.id,
                    name=normalized_name,
                    layers=layers,
                    created_at=preset.created_at,
                    updated_at=now,
                )
                updated_payload.append(self._sound_preset_payload(updated_preset))
            else:
                updated_payload.append(self._sound_preset_payload(preset))
        if updated_preset is None:
            updated_preset = SoundPreset(
                id=str(uuid4()),
                name=normalized_name,
                layers=layers,
                created_at=now,
                updated_at=now,
            )
            updated_payload.append(self._sound_preset_payload(updated_preset))
        self.set_state("sound_presets", updated_payload)
        return updated_preset

    def delete_sound_preset(self, preset_id: str) -> None:
        payload = [
            self._sound_preset_payload(preset)
            for preset in self.list_sound_presets()
            if preset.id != preset_id
        ]
        self.set_state("sound_presets", payload)

    def _sound_preset_payload(self, preset: SoundPreset) -> dict[str, Any]:
        return {
            "id": preset.id,
            "name": preset.name,
            "created_at": preset.created_at,
            "updated_at": preset.updated_at,
            "layers": [
                {
                    "sound_id": int(layer.sound_id),
                    "volume_percent": max(0, min(int(layer.volume_percent), 100)),
                }
                for layer in preset.layers
            ],
        }

    def get_title_rules(self) -> list[TitleMatchRule]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM title_match_rules ORDER BY id ASC"
            ).fetchall()
        return [
            TitleMatchRule(
                id=row["id"],
                enabled=bool(row["enabled"]),
                match_type=row["match_type"],
                match_text=row["match_text"],
                case_sensitive=bool(row["case_sensitive"]),
                trim_whitespace=bool(row["trim_whitespace"]),
                ignore_cancelled=bool(row["ignore_cancelled"]),
                ignore_transparent=bool(row["ignore_transparent"]),
            )
            for row in rows
        ]

    def add_title_rule(
        self,
        enabled: bool,
        match_type: str,
        match_text: str,
        case_sensitive: bool,
        trim_whitespace: bool,
        ignore_cancelled: bool,
        ignore_transparent: bool,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO title_match_rules(
                    enabled, match_type, match_text, case_sensitive,
                    trim_whitespace, ignore_cancelled, ignore_transparent,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(enabled),
                    match_type,
                    match_text,
                    int(case_sensitive),
                    int(trim_whitespace),
                    int(ignore_cancelled),
                    int(ignore_transparent),
                    utcnow_iso(),
                    utcnow_iso(),
                ),
            )

    def delete_title_rule(self, rule_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM title_match_rules WHERE id = ?", (rule_id,))

    def list_calendars(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM calendars ORDER BY enabled DESC, display_name ASC, calendar_id ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_calendar(
        self,
        calendar_id: str,
        display_name: str | None,
        enabled: bool = True,
    ) -> None:
        now = utcnow_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO calendars(calendar_id, display_name, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(calendar_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (calendar_id, display_name, int(enabled), now, now),
            )

    def set_calendar_enabled(self, calendar_id: str, enabled: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE calendars SET enabled = ?, updated_at = ? WHERE calendar_id = ?",
                (int(enabled), utcnow_iso(), calendar_id),
            )

    def enabled_calendar_ids(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT calendar_id FROM calendars WHERE enabled = 1 ORDER BY calendar_id"
            ).fetchall()
        return [row["calendar_id"] for row in rows]

    def list_ics_feeds(self) -> list[dict[str, Any]]:
        return list(self.get_state("ics_feeds", []))

    def enabled_ics_feeds(self) -> list[dict[str, Any]]:
        return [
            feed for feed in self.list_ics_feeds() if feed.get("enabled", True)
        ]

    def add_ics_feed(self, label: str, location: str) -> None:
        feeds = self.list_ics_feeds()
        feeds.append(
            {
                "id": str(uuid4()),
                "label": label.strip() or location.strip(),
                "location": location.strip(),
                "enabled": True,
            }
        )
        self.set_state("ics_feeds", feeds)

    def set_ics_feed_enabled(self, feed_id: str, enabled: bool) -> None:
        feeds = self.list_ics_feeds()
        for feed in feeds:
            if feed.get("id") == feed_id:
                feed["enabled"] = enabled
        self.set_state("ics_feeds", feeds)

    def delete_ics_feed(self, feed_id: str) -> None:
        feeds = [
            feed for feed in self.list_ics_feeds() if feed.get("id") != feed_id
        ]
        self.set_state("ics_feeds", feeds)

    def save_calendar_account(
        self,
        provider: str,
        token_path: str,
        account_email: str | None,
    ) -> None:
        now = utcnow_iso()
        with self.connect() as conn:
            conn.execute("DELETE FROM calendar_accounts WHERE provider = ?", (provider,))
            conn.execute(
                """
                INSERT INTO calendar_accounts(
                    provider, account_email, token_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (provider, account_email, token_path, now, now),
            )

    def get_calendar_account(self, provider: str = "google") -> CalendarAccount | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM calendar_accounts WHERE provider = ? LIMIT 1",
                (provider,),
            ).fetchone()
        if row is None:
            return None
        return CalendarAccount(
            id=row["id"],
            provider=row["provider"],
            account_email=row["account_email"],
            token_path=row["token_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def clear_calendar_account(self, provider: str = "google") -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM calendar_accounts WHERE provider = ?", (provider,))

    def replace_trigger_cache(
        self,
        source: str,
        blocks: list[TriggerBlock],
        start_buffer_minutes: int,
        end_buffer_minutes: int,
    ) -> None:
        now = utcnow_iso()
        with self.connect() as conn:
            conn.execute("DELETE FROM trigger_cache WHERE source = ?", (source,))
            for block in blocks:
                display_start = block.display_start_time or block.start_time
                display_end = block.display_end_time or block.end_time
                buffered_start = display_start - timedelta(minutes=start_buffer_minutes)
                buffered_end = display_end + timedelta(minutes=end_buffer_minutes)
                conn.execute(
                    """
                    INSERT INTO trigger_cache(
                        source, calendar_id, event_id_hash, summary_hash,
                        start_time, end_time, buffered_start_time, buffered_end_time,
                        matched_rule_id, created_at, last_seen
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source,
                        block.calendar_id,
                        block.event_id_hash,
                        block.summary_hash,
                        display_start.isoformat(),
                        display_end.isoformat(),
                        buffered_start.isoformat(),
                        buffered_end.isoformat(),
                        block.matched_rule_id,
                        now,
                        now,
                    ),
                )

    def get_cached_blocks(self, source: str) -> list[TriggerBlock]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT start_time,
                       end_time,
                       COALESCE(buffered_start_time, start_time) AS buffered_start_time,
                       COALESCE(buffered_end_time, end_time) AS buffered_end_time,
                       calendar_id,
                       event_id_hash,
                       summary_hash,
                       matched_rule_id,
                       source
                FROM trigger_cache
                WHERE source = ?
                ORDER BY buffered_start_time ASC
                """,
                (source,),
            ).fetchall()
        return [
            TriggerBlock(
                start_time=datetime.fromisoformat(row["buffered_start_time"]),
                end_time=datetime.fromisoformat(row["buffered_end_time"]),
                display_start_time=datetime.fromisoformat(row["start_time"]),
                display_end_time=datetime.fromisoformat(row["end_time"]),
                source=row["source"],
                calendar_id=row["calendar_id"],
                event_id_hash=row["event_id_hash"],
                summary_hash=row["summary_hash"],
                matched_rule_id=row["matched_rule_id"],
            )
            for row in rows
        ]

    def get_cached_calendar_blocks(self, source: str) -> list[TriggerBlock]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT start_time, end_time, calendar_id,
                       event_id_hash, summary_hash, matched_rule_id, source
                FROM trigger_cache
                WHERE source = ?
                ORDER BY start_time ASC
                """,
                (source,),
            ).fetchall()
        return [
            TriggerBlock(
                start_time=datetime.fromisoformat(row["start_time"]),
                end_time=datetime.fromisoformat(row["end_time"]),
                source=row["source"],
                calendar_id=row["calendar_id"],
                event_id_hash=row["event_id_hash"],
                summary_hash=row["summary_hash"],
                matched_rule_id=row["matched_rule_id"],
            )
            for row in rows
        ]


def init_db(config: AppConfig) -> Database:
    database = Database(config.paths.database)
    database.init()
    return database
