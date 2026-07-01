from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.display import format_time_label
from tzlocal import get_localzone_name

SYSTEM_TIMEZONE = "system"


def system_timezone_name() -> str:
    try:
        return get_localzone_name()
    except Exception:
        return "UTC"


def normalize_timezone_name(raw_value: str | None) -> str:
    value = (raw_value or "").strip()
    return value or SYSTEM_TIMEZONE


def validate_timezone_name(raw_value: str | None) -> str:
    value = normalize_timezone_name(raw_value)
    if value == SYSTEM_TIMEZONE:
        return value
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            "Timezone must be a valid IANA name like America/New_York."
        ) from exc
    return value


def effective_timezone_name(raw_value: str | None) -> str:
    value = normalize_timezone_name(raw_value)
    if value == SYSTEM_TIMEZONE:
        return system_timezone_name()
    return value


def resolve_timezone(raw_value: str | None) -> tzinfo:
    try:
        return ZoneInfo(effective_timezone_name(raw_value))
    except ZoneInfoNotFoundError:
        return timezone.utc


def timezone_offset_label(value: datetime) -> str:
    offset = value.utcoffset() or timedelta()
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    if minutes:
        return f"GMT{sign}{hours:02d}:{minutes:02d}"
    return f"GMT{sign}{hours:02d}"


def timezone_context(
    raw_value: str | None,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    stored_name = normalize_timezone_name(raw_value)
    effective_name = effective_timezone_name(stored_name)
    current_time = (now or datetime.now(timezone.utc)).astimezone(
        resolve_timezone(stored_name)
    )
    return {
        "stored_name": stored_name,
        "effective_name": effective_name,
        "system_name": system_timezone_name(),
        "uses_system": stored_name == SYSTEM_TIMEZONE,
        "offset_label": timezone_offset_label(current_time),
        "current_time_label": format_time_label(current_time),
    }


def localize_datetime(value: datetime, raw_value: str | None) -> datetime:
    return value.astimezone(resolve_timezone(raw_value))
