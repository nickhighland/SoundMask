from __future__ import annotations

from tempfile import TemporaryDirectory

from app.calendar_client import FREEBUSY_SCOPES, GoogleCalendarClient, TITLE_MATCH_SCOPES
from app.config import AppConfig, AppPaths


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


def test_freebusy_mode_requests_busy_and_readonly_scopes():
    with TemporaryDirectory() as temp_dir:
        client = GoogleCalendarClient(make_config(temp_dir))

        assert client.scopes_for_mode("freebusy") == FREEBUSY_SCOPES


def test_title_match_mode_requests_readonly_scope():
    with TemporaryDirectory() as temp_dir:
        client = GoogleCalendarClient(make_config(temp_dir))

        assert client.scopes_for_mode("title_match") == TITLE_MATCH_SCOPES
