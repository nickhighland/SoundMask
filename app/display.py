from __future__ import annotations

from datetime import date, datetime, time


def _coerce_temporal(
    value: date | datetime | time | str | None,
) -> date | datetime | time | str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date, time)):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    try:
        return time.fromisoformat(text)
    except ValueError:
        return value


def format_date_label(
    value: date | datetime | str | None,
) -> str | None:
    parsed = _coerce_temporal(value)
    if parsed is None:
        return None
    if isinstance(parsed, str):
        return parsed
    if isinstance(parsed, datetime):
        parsed = parsed.date()
    if isinstance(parsed, date):
        return parsed.strftime("%B %d, %Y").replace(" 0", " ")
    return str(parsed)


def format_time_label(
    value: datetime | time | str | None,
) -> str | None:
    parsed = _coerce_temporal(value)
    if parsed is None:
        return None
    if isinstance(parsed, str):
        return parsed
    if isinstance(parsed, datetime):
        parsed = parsed.timetz().replace(tzinfo=None)
    if isinstance(parsed, time):
        return parsed.strftime("%I:%M %p").lstrip("0")
    return str(parsed)


def format_datetime_label(
    value: datetime | str | None,
) -> str | None:
    parsed = _coerce_temporal(value)
    if parsed is None:
        return None
    if isinstance(parsed, str):
        return parsed
    if isinstance(parsed, datetime):
        date_label = format_date_label(parsed)
        time_label = format_time_label(parsed)
        if date_label and time_label:
            return f"{date_label} at {time_label}"
        return date_label or time_label
    if isinstance(parsed, date):
        return format_date_label(parsed)
    return str(parsed)
