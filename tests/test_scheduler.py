from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.audio import AudioManager
from app.calendar_client import GoogleCalendarClient, IcsCalendarClient
from app.config import AppConfig, AppPaths
from app.db import init_db
from app.scheduler import SoundMaskScheduler


def test_fake_block_persists_and_survives_sync():
    with TemporaryDirectory() as temp_dir:
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
        db = init_db(config)
        db.set_setting("trigger_mode", "fake")
        scheduler = SoundMaskScheduler(
            db,
            AudioManager(Path(paths.logs) / "mpv.sock"),
            GoogleCalendarClient(config),
            IcsCalendarClient(config),
        )
        scheduler.add_fake_block(1, 3)
        assert db.get_state("fake_blocks")
        scheduler.sync_cycle()
        assert scheduler.current_blocks


def test_ics_source_syncs_local_feed():
    with TemporaryDirectory() as temp_dir:
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

        start_time = datetime.now(timezone.utc) + timedelta(minutes=30)
        end_time = start_time + timedelta(hours=1)
        ics_path = Path(temp_dir) / "office.ics"
        ics_path.write_text(
            "\n".join(
                [
                    "BEGIN:VCALENDAR",
                    "VERSION:2.0",
                    "PRODID:-//SoundMask Tests//EN",
                    "BEGIN:VEVENT",
                    "UID:ics-test-1",
                    "DTSTAMP:20260629T120000Z",
                    f"DTSTART:{start_time.strftime('%Y%m%dT%H%M%SZ')}",
                    f"DTEND:{end_time.strftime('%Y%m%dT%H%M%SZ')}",
                    "SUMMARY:Counseling appointment",
                    "END:VEVENT",
                    "END:VCALENDAR",
                ]
            ),
            encoding="utf-8",
        )

        db = init_db(config)
        db.set_setting("trigger_mode", "freebusy")
        db.set_setting("calendar_source", "ics")
        db.add_ics_feed("Office", str(ics_path))
        scheduler = SoundMaskScheduler(
            db,
            AudioManager(Path(paths.logs) / "mpv.sock"),
            GoogleCalendarClient(config),
            IcsCalendarClient(config),
        )

        scheduler.sync_cycle()

        assert scheduler.last_sync_ok is True
        assert len(scheduler.current_blocks) == 1
        assert db.get_cached_blocks("ics:freebusy")


def test_init_db_migrates_legacy_trigger_cache_schema():
    with TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "SoundMask.sqlite"
        with sqlite3.connect(database_path) as conn:
            conn.executescript(
                """
                CREATE TABLE trigger_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    calendar_id TEXT,
                    event_id_hash TEXT,
                    summary_hash TEXT,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    matched_rule_id INTEGER,
                    created_at TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                );
                INSERT INTO trigger_cache(
                    source, calendar_id, event_id_hash, summary_hash,
                    start_time, end_time, matched_rule_id, created_at, last_seen
                )
                VALUES (
                    'ics:freebusy',
                    'primary',
                    'event-1',
                    'summary-1',
                    '2026-06-29T13:00:00+00:00',
                    '2026-06-29T14:00:00+00:00',
                    1,
                    '2026-06-29T12:00:00+00:00',
                    '2026-06-29T12:00:00+00:00'
                );
                """
            )

        paths = AppPaths(
            root=temp_dir,
            database=str(database_path),
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

        db = init_db(config)

        cached_blocks = db.get_cached_blocks("ics:freebusy")

        assert cached_blocks
        assert cached_blocks[0].start_time.isoformat() == "2026-06-29T13:00:00+00:00"
        assert cached_blocks[0].end_time.isoformat() == "2026-06-29T14:00:00+00:00"
