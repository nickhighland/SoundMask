from __future__ import annotations

import os
from datetime import datetime, timezone
from tempfile import TemporaryDirectory

from app.config import AppConfig, AppPaths
from app.log_viewer import available_sources, read_log_source


def make_config(temp_dir: str) -> AppConfig:
    return AppConfig(
        env="test",
        host="127.0.0.1",
        port=8080,
        session_secret="test-secret",
        google_client_secret=None,
        paths=AppPaths(
            root=temp_dir,
            database=f"{temp_dir}/SoundMask.sqlite",
            sounds=f"{temp_dir}/sounds",
            tokens=f"{temp_dir}/tokens",
            logs=f"{temp_dir}/logs",
        ),
    )


def test_available_sources_include_expected_logs():
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)

        sources = available_sources(config)

        assert [source.key for source in sources] == ["app", "service", "updates"]


def test_read_log_source_tails_recent_lines():
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        config.paths.logs.mkdir(parents=True, exist_ok=True)
        log_file = config.paths.logs / "soundmask.log"
        log_file.write_text("one\ntwo\nthree\n", encoding="utf-8")

        payload = read_log_source(config, "app", lines=2)

        assert payload["source"] == "app"
        assert payload["content"] == "two\nthree"
        assert payload["modified_at"] is not None


def test_read_log_source_localizes_modified_and_refresh_timestamps(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        config.paths.logs.mkdir(parents=True, exist_ok=True)
        log_file = config.paths.logs / "soundmask.log"
        log_file.write_text("one\n", encoding="utf-8")
        fixed_utc = datetime(2026, 7, 1, 17, 0, tzinfo=timezone.utc)
        timestamp = fixed_utc.timestamp()
        os.utime(log_file, (timestamp, timestamp))

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    return cls(2026, 7, 1, 17, 0)
                return fixed_utc.astimezone(tz)

        monkeypatch.setattr("app.log_viewer.datetime", FixedDateTime)

        payload = read_log_source(
            config,
            "app",
            lines=10,
            timezone_name="America/New_York",
        )

        assert payload["modified_at"] == "July 1, 2026 at 1:00 PM"
        assert payload["updated_at"] == "July 1, 2026 at 1:00 PM"
