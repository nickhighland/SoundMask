from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.audio import AudioManager
from app.calendar_client import GoogleCalendarClient, IcsCalendarClient
from app.config import AppConfig, AppPaths
from app.db import init_db
from app.models import TriggerBlock
from app.scheduler import SoundMaskScheduler
from app.sound_mixer import SoundMixManager


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
            SoundMixManager(Path(paths.root) / "mixes"),
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
            SoundMixManager(Path(paths.root) / "mixes"),
        )

        scheduler.sync_cycle()

        assert scheduler.last_sync_ok is True
        assert len(scheduler.current_blocks) == 1
        assert db.get_cached_blocks("ics:freebusy")


def test_ics_title_match_sync_keeps_adjacent_appointments_distinct_in_cache():
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

        start_time = datetime.now(timezone.utc).replace(
            minute=0,
            second=0,
            microsecond=0,
        ) + timedelta(hours=1)
        second_start = start_time + timedelta(hours=1)
        ics_path = Path(temp_dir) / "adjacent-title-match.ics"
        ics_path.write_text(
            "\n".join(
                [
                    "BEGIN:VCALENDAR",
                    "VERSION:2.0",
                    "PRODID:-//SoundMask Tests//EN",
                    "BEGIN:VEVENT",
                    "UID:ics-title-1",
                    "DTSTAMP:20260629T120000Z",
                    f"DTSTART:{start_time.strftime('%Y%m%dT%H%M%SZ')}",
                    f"DTEND:{(start_time + timedelta(hours=1)).strftime('%Y%m%dT%H%M%SZ')}",
                    "SUMMARY:Counseling appointment",
                    "END:VEVENT",
                    "BEGIN:VEVENT",
                    "UID:ics-title-2",
                    "DTSTAMP:20260629T120000Z",
                    f"DTSTART:{second_start.strftime('%Y%m%dT%H%M%SZ')}",
                    f"DTEND:{(second_start + timedelta(hours=1)).strftime('%Y%m%dT%H%M%SZ')}",
                    "SUMMARY:Counseling appointment",
                    "END:VEVENT",
                    "END:VCALENDAR",
                ]
            ),
            encoding="utf-8",
        )

        db = init_db(config)
        db.set_setting("trigger_mode", "title_match")
        db.set_setting("calendar_source", "ics")
        db.add_title_rule(
            enabled=True,
            match_type="exact",
            match_text="Counseling appointment",
            case_sensitive=False,
            trim_whitespace=True,
            ignore_cancelled=True,
            ignore_transparent=True,
        )
        db.add_ics_feed("Office", str(ics_path))

        scheduler = SoundMaskScheduler(
            db,
            AudioManager(Path(paths.logs) / "mpv.sock"),
            GoogleCalendarClient(config),
            IcsCalendarClient(config),
            SoundMixManager(Path(paths.root) / "mixes"),
        )

        scheduler.sync_cycle()

        assert scheduler.last_sync_ok is True
        assert len(scheduler.calendar_blocks) == 2
        assert scheduler.calendar_blocks[0].start_time == start_time
        assert scheduler.calendar_blocks[0].end_time == start_time + timedelta(hours=1)
        assert scheduler.calendar_blocks[1].start_time == second_start
        assert scheduler.calendar_blocks[1].end_time == second_start + timedelta(hours=1)
        assert len(scheduler.current_blocks) == 1

        cached_calendar_blocks = db.get_cached_calendar_blocks("ics:title_match")
        assert len(cached_calendar_blocks) == 2
        assert cached_calendar_blocks[0].start_time == start_time
        assert cached_calendar_blocks[0].end_time == start_time + timedelta(hours=1)
        assert cached_calendar_blocks[1].start_time == second_start
        assert cached_calendar_blocks[1].end_time == second_start + timedelta(hours=1)


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


def test_google_freebusy_uses_display_blocks_for_calendar_view(monkeypatch):
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
        db.set_setting("trigger_mode", "freebusy")
        db.set_setting("calendar_source", "google")
        db.upsert_calendar("primary", "Primary", enabled=True)

        scheduler = SoundMaskScheduler(
            db,
            AudioManager(Path(paths.logs) / "mpv.sock"),
            GoogleCalendarClient(config),
            IcsCalendarClient(config),
            SoundMixManager(Path(paths.root) / "mixes"),
        )
        now = datetime.now(timezone.utc).replace(microsecond=0)
        playback_block = TriggerBlock(
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=9),
            source="freebusy",
        )
        display_blocks = [
            TriggerBlock(
                start_time=now + timedelta(hours=offset),
                end_time=now + timedelta(hours=offset + 1),
                source="freebusy",
            )
            for offset in range(2, 9)
        ]

        monkeypatch.setattr(
            scheduler.calendar_client,
            "fetch_freebusy_blocks",
            lambda calendar_ids, time_min, time_max: [playback_block],
        )
        monkeypatch.setattr(
            scheduler.calendar_client,
            "fetch_display_blocks",
            lambda calendar_ids, time_min, time_max: display_blocks,
        )

        scheduler.sync_cycle()

        assert len(scheduler.calendar_blocks) == 7
        assert scheduler.calendar_blocks[0].start_time == display_blocks[0].start_time
        assert len(scheduler.current_blocks) == 1


def test_sync_window_bounds_start_at_local_day():
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

        scheduler = SoundMaskScheduler(
            init_db(config),
            AudioManager(Path(paths.logs) / "mpv.sock"),
            GoogleCalendarClient(config),
            IcsCalendarClient(config),
            SoundMixManager(Path(paths.root) / "mixes"),
        )
        scheduler.db.set_setting("timezone_name", "America/New_York")
        now = datetime(2026, 7, 1, 3, 15, tzinfo=timezone.utc)

        window_start, window_end = scheduler._sync_window_bounds(
            scheduler.db.get_settings(),
            now=now,
        )

        assert window_start == datetime(2026, 6, 30, 4, 0, tzinfo=timezone.utc)
        assert window_end == now + timedelta(hours=scheduler.LOOKAHEAD_HOURS)
