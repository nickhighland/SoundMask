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
