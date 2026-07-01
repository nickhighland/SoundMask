from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import TriggerBlock
from app.routes.dashboard import _normalized_volume_percent, build_schedule_view


def test_build_schedule_view_marks_active_and_upcoming_windows():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    blocks = [
        TriggerBlock(
            start_time=now - timedelta(minutes=15),
            end_time=now + timedelta(minutes=45),
            source="ics_title_match",
        ),
        TriggerBlock(
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=3),
            source="freebusy",
        ),
    ]

    view = build_schedule_view(blocks, now=now)

    assert len(view["entries"]) == 2
    assert view["entries"][0]["active"] is True
    assert view["entries"][0]["source_label"] == "ICS title match"
    assert view["entries"][1]["source_label"] == "Google FreeBusy"
    assert len(view["timeline_segments"]) == 2
    assert 0 <= view["now_percent"] <= 100


def test_dashboard_volume_normalization_clamps_to_supported_range():
    assert _normalized_volume_percent(-5) == 0
    assert _normalized_volume_percent(80) == 80
    assert _normalized_volume_percent(999) == 150
