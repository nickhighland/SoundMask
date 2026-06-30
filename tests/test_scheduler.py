from __future__ import annotations

from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory
from pathlib import Path

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
