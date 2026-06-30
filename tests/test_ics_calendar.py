from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.calendar_client import IcsCalendarClient
from app.config import AppConfig, AppPaths
from app.models import TitleMatchRule


def make_client(temp_dir: str) -> IcsCalendarClient:
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
    return IcsCalendarClient(config)


def write_feed(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines), encoding="utf-8")


def test_ics_freebusy_expands_recurring_events():
    with TemporaryDirectory() as temp_dir:
        client = make_client(temp_dir)
        feed_path = Path(temp_dir) / "recurring.ics"
        write_feed(
            feed_path,
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//SoundMask Tests//EN",
                "BEGIN:VEVENT",
                "UID:recurring-1",
                "DTSTAMP:20260629T120000Z",
                "DTSTART:20260629T140000Z",
                "DTEND:20260629T150000Z",
                "RRULE:FREQ=DAILY;COUNT=3",
                "SUMMARY:Recurring counseling appointment",
                "END:VEVENT",
                "END:VCALENDAR",
            ],
        )

        blocks = client.fetch_freebusy_blocks(
            [{"id": "feed-1", "location": str(feed_path)}],
            datetime(2026, 6, 29, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 23, 59, tzinfo=timezone.utc),
            ignore_all_day_events=True,
        )

        assert len(blocks) == 3
        assert [block.start_time.day for block in blocks] == [29, 30, 1]
        assert all(block.source == "ics_freebusy" for block in blocks)


def test_ics_title_match_ignores_all_day_events_when_configured():
    with TemporaryDirectory() as temp_dir:
        client = make_client(temp_dir)
        feed_path = Path(temp_dir) / "all-day.ics"
        write_feed(
            feed_path,
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//SoundMask Tests//EN",
                "BEGIN:VEVENT",
                "UID:all-day-1",
                "DTSTAMP:20260629T120000Z",
                "DTSTART;VALUE=DATE:20260630",
                "DTEND;VALUE=DATE:20260701",
                "SUMMARY:Counseling appointment",
                "END:VEVENT",
                "BEGIN:VEVENT",
                "UID:timed-1",
                "DTSTAMP:20260629T120000Z",
                "DTSTART:20260630T170000Z",
                "DTEND:20260630T180000Z",
                "SUMMARY:Counseling appointment",
                "END:VEVENT",
                "END:VCALENDAR",
            ],
        )
        rules = [
            TitleMatchRule(
                id=1,
                enabled=True,
                match_type="exact",
                match_text="Counseling appointment",
            )
        ]

        blocks = client.fetch_title_match_blocks(
            [{"id": "feed-1", "location": str(feed_path)}],
            datetime(2026, 6, 29, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 1, 23, 59, tzinfo=timezone.utc),
            rules,
            debug_store_event_summaries=False,
            ignore_all_day_events=True,
        )

        assert len(blocks) == 1
        assert blocks[0].is_all_day is False


def test_ics_title_match_hashes_each_recurring_instance():
    with TemporaryDirectory() as temp_dir:
        client = make_client(temp_dir)
        feed_path = Path(temp_dir) / "title-match.ics"
        write_feed(
            feed_path,
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//SoundMask Tests//EN",
                "BEGIN:VEVENT",
                "UID:rule-1",
                "DTSTAMP:20260629T120000Z",
                "DTSTART:20260629T140000Z",
                "DTEND:20260629T150000Z",
                "RRULE:FREQ=DAILY;COUNT=2",
                "SUMMARY:Counseling appointment",
                "END:VEVENT",
                "BEGIN:VEVENT",
                "UID:rule-2",
                "DTSTAMP:20260629T120000Z",
                "DTSTART:20260629T160000Z",
                "DTEND:20260629T170000Z",
                "SUMMARY:Admin block",
                "END:VEVENT",
                "END:VCALENDAR",
            ],
        )
        rules = [
            TitleMatchRule(
                id=9,
                enabled=True,
                match_type="exact",
                match_text="Counseling appointment",
            )
        ]

        blocks = client.fetch_title_match_blocks(
            [{"id": "feed-1", "location": str(feed_path)}],
            datetime(2026, 6, 29, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 1, 23, 59, tzinfo=timezone.utc),
            rules,
            debug_store_event_summaries=False,
            ignore_all_day_events=True,
        )

        assert len(blocks) == 2
        assert {block.matched_rule_id for block in blocks} == {9}
        assert len({block.event_id_hash for block in blocks}) == 2
