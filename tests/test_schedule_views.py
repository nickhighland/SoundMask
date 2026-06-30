from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import TriggerBlock
from app.schedule_views import build_calendar_view, build_schedule_view


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
    assert view["days"][0]["agenda_items"]
    assert view["days"][1]["agenda_items"]
    assert view["has_blocks"] is True
