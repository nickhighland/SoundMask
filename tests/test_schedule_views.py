from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import TriggerBlock
from app.schedule_views import (
    appointment_time_range_label,
    build_calendar_view,
    build_schedule_view,
)


def test_build_schedule_view_marks_active_segments():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    blocks = [
        TriggerBlock(
            start_time=now - timedelta(minutes=10),
            end_time=now + timedelta(minutes=40),
            source="ics_title_match",
        )
    ]

    view = build_schedule_view(blocks, now=now)

    assert view["entries"][0]["active"] is True
    assert view["timeline_segments"][0]["active"] is True


def test_build_schedule_view_uses_configured_timezone():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    blocks = [
        TriggerBlock(
            start_time=datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 19, 0, tzinfo=timezone.utc),
            source="ics_title_match",
        )
    ]

    view = build_schedule_view(blocks, now=now, timezone_name="America/Los_Angeles")

    assert view["entries"][0]["start_label"] == "10:00 AM"
    assert view["entries"][0]["end_label"] == "11:00 AM"


def test_build_schedule_view_keeps_completed_sessions_from_today():
    now = datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc)
    blocks = [
        TriggerBlock(
            start_time=now - timedelta(hours=3),
            end_time=now - timedelta(hours=2),
            source="ics_title_match",
        ),
        TriggerBlock(
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            source="freebusy",
        ),
    ]

    view = build_schedule_view(blocks, now=now)

    assert len(view["entries"]) == 2
    assert view["entries"][0]["active"] is False
    assert len(view["timeline_segments"]) == 2


def test_build_calendar_view_groups_blocks_by_day():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    blocks = [
        TriggerBlock(
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            source="freebusy",
        ),
        TriggerBlock(
            start_time=now + timedelta(days=1, hours=2),
            end_time=now + timedelta(days=1, hours=3),
            source="ics_freebusy",
        ),
    ]

    view = build_calendar_view(blocks, now=now, days=3)

    assert len(view["days"]) == 3
    assert view["days"][0]["events"]
    assert view["days"][1]["events"]
    assert view["days"][0]["events"][0]["title_label"] == "Counseling appointment"
    assert view["has_blocks"] is True


def test_build_calendar_view_uses_original_appointment_window():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    blocks = [
        TriggerBlock(
            start_time=now + timedelta(minutes=58),
            end_time=now + timedelta(hours=2, minutes=3),
            display_start_time=now + timedelta(hours=1),
            display_end_time=now + timedelta(hours=2),
            source="ics_title_match",
        )
    ]

    view = build_calendar_view(blocks, now=now, days=1)

    expected_label = appointment_time_range_label(
        blocks[0].display_start_time.astimezone(),
        blocks[0].display_end_time.astimezone(),
    )

    assert view["days"][0]["events"][0]["time_label"] == expected_label


def test_build_calendar_view_splits_overlapping_events_into_columns():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    blocks = [
        TriggerBlock(
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            source="title_match",
        ),
        TriggerBlock(
            start_time=now + timedelta(hours=1, minutes=30),
            end_time=now + timedelta(hours=2, minutes=30),
            source="ics_title_match",
        ),
    ]

    view = build_calendar_view(blocks, now=now, days=1)
    first_event, second_event = view["days"][0]["events"]

    assert first_event["width_percent"] == 50.0
    assert second_event["width_percent"] == 50.0
    assert second_event["left_percent"] == 50.0


def test_build_calendar_view_prefers_hour_slots_over_aggregate_block():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    long_block_start = now + timedelta(hours=2)
    blocks = [
        TriggerBlock(
            start_time=long_block_start,
            end_time=long_block_start + timedelta(hours=7),
            source="freebusy",
        ),
    ]
    for hour in range(3, 9):
        blocks.append(
            TriggerBlock(
                start_time=now + timedelta(hours=hour),
                end_time=now + timedelta(hours=hour + 1),
                source="freebusy",
            )
    )

    view = build_calendar_view(blocks, now=now, days=1)

    assert [event["time_label"] for event in view["days"][0]["events"]] == [
        appointment_time_range_label(
            (now + timedelta(hours=hour)).astimezone(),
            (now + timedelta(hours=hour + 1)).astimezone(),
        )
        for hour in range(2, 9)
    ]


def test_build_calendar_view_keeps_distinct_calendar_overlap():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    long_block_start = now + timedelta(hours=2)
    blocks = [
        TriggerBlock(
            start_time=long_block_start,
            end_time=long_block_start + timedelta(hours=7),
            source="freebusy",
            calendar_id="primary",
        ),
    ]
    for hour in range(3, 9):
        blocks.append(
            TriggerBlock(
                start_time=now + timedelta(hours=hour),
                end_time=now + timedelta(hours=hour + 1),
                source="freebusy",
                calendar_id="secondary",
            )
        )

    view = build_calendar_view(blocks, now=now, days=1)

    assert view["days"][0]["events"][0]["time_label"] == appointment_time_range_label(
        long_block_start.astimezone(),
        (long_block_start + timedelta(hours=7)).astimezone(),
    )


def test_build_calendar_view_uses_configured_timezone_label():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    view = build_calendar_view([], now=now, days=1, timezone_name="America/Los_Angeles")

    assert view["timezone_label"] == "GMT-08"
