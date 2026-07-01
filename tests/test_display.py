from __future__ import annotations

from datetime import datetime, timezone

from app.display import format_date_label, format_datetime_label, format_time_label


def test_format_date_label_uses_month_day_year() -> None:
    value = datetime(2026, 7, 1, 13, 0, tzinfo=timezone.utc)

    assert format_date_label(value) == "July 1, 2026"


def test_format_time_label_keeps_hours_and_minutes() -> None:
    value = datetime(2026, 7, 1, 13, 0, tzinfo=timezone.utc)

    assert format_time_label(value) == "1:00 PM"


def test_format_datetime_label_combines_date_and_time() -> None:
    value = datetime(2026, 7, 1, 13, 0, tzinfo=timezone.utc)

    assert format_datetime_label(value) == "July 1, 2026 at 1:00 PM"
