from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.models import TriggerBlock


def source_label(source: str) -> str:
    labels = {
        "fake": "Fake mode",
        "freebusy": "Google FreeBusy",
        "title_match": "Google title match",
        "ics_freebusy": "ICS busy window",
        "ics_title_match": "ICS title match",
    }
    return labels.get(source, source.replace("_", " ").title())


def time_label(value: datetime, include_meridiem: bool = True) -> str:
    pattern = "%I:%M %p" if include_meridiem else "%I:%M"
    return value.strftime(pattern).lstrip("0")


def _day_title(day_value: date, today: date) -> str:
    if day_value == today:
        return "Today"
    if day_value == today + timedelta(days=1):
        return "Tomorrow"
    return day_value.strftime("%A")


def build_schedule_view(
    blocks: list[TriggerBlock],
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    local_now = current_time.astimezone()
    local_tz = local_now.tzinfo or timezone.utc
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    day_span_seconds = max(1, int((day_end - day_start).total_seconds()))

    entries: list[dict[str, Any]] = []
    timeline_segments: list[dict[str, Any]] = []
    for block in sorted(blocks, key=lambda item: item.start_time):
        start_local = block.start_time.astimezone(local_tz)
        end_local = block.end_time.astimezone(local_tz)
        if end_local < local_now - timedelta(minutes=1):
            continue

        active = block.start_time <= current_time <= block.end_time
        day_name = (
            "Today"
            if start_local.date() == local_now.date()
            else "Tomorrow"
            if start_local.date() == (local_now.date() + timedelta(days=1))
            else start_local.strftime("%a, %b %d")
        )
        duration_minutes = max(
            1,
            int((block.end_time - block.start_time).total_seconds() / 60),
        )
        entries.append(
            {
                "start_label": time_label(start_local),
                "end_label": time_label(end_local),
                "day_label": day_name,
                "duration_label": f"{duration_minutes} min",
                "source_label": source_label(block.source),
                "active": active,
            }
        )

        clip_start = max(start_local, day_start)
        clip_end = min(end_local, day_end)
        if clip_end <= clip_start:
            continue
        left = ((clip_start - day_start).total_seconds() / day_span_seconds) * 100
        width = max(
            2,
            ((clip_end - clip_start).total_seconds() / day_span_seconds) * 100,
        )
        timeline_segments.append(
            {
                "left": round(left, 2),
                "width": round(width, 2),
                "label": (
                    f"{time_label(start_local, include_meridiem=False)}-"
                    f"{time_label(end_local)}"
                ),
                "active": active,
                "source_label": source_label(block.source),
            }
        )

    timeline_hours = [
        time_label(day_start + timedelta(hours=hour)).replace(":00", "")
        for hour in range(0, 24, 3)
    ]
    return {
        "entries": entries[:8],
        "timeline_segments": timeline_segments,
        "timeline_hours": timeline_hours,
        "now_percent": max(
            0,
            min(
                100,
                round(
                    ((local_now - day_start).total_seconds() / day_span_seconds) * 100,
                    2,
                ),
            ),
        ),
        "now_label": time_label(local_now),
    }


def build_calendar_view(
    blocks: list[TriggerBlock],
    now: datetime | None = None,
    days: int = 4,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    local_now = current_time.astimezone()
    local_tz = local_now.tzinfo or timezone.utc
    today = local_now.date()
    day_cards: list[dict[str, Any]] = []

    sorted_blocks = sorted(blocks, key=lambda item: item.start_time)
    for offset in range(days):
        day_start = local_now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ) + timedelta(days=offset)
        day_end = day_start + timedelta(days=1)
        day_segments: list[dict[str, Any]] = []
        agenda_items: list[dict[str, Any]] = []
        day_seconds = max(1, int((day_end - day_start).total_seconds()))

        for block in sorted_blocks:
            start_local = block.start_time.astimezone(local_tz)
            end_local = block.end_time.astimezone(local_tz)
            if end_local <= day_start or start_local >= day_end:
                continue

            clip_start = max(start_local, day_start)
            clip_end = min(end_local, day_end)
            top = ((clip_start - day_start).total_seconds() / day_seconds) * 100
            height = max(
                3,
                ((clip_end - clip_start).total_seconds() / day_seconds) * 100,
            )
            active = block.start_time <= current_time <= block.end_time
            segment = {
                "top": round(top, 2),
                "height": round(height, 2),
                "start_label": time_label(start_local),
                "end_label": time_label(end_local),
                "source_label": source_label(block.source),
                "active": active,
            }
            day_segments.append(segment)
            agenda_items.append(segment)

        day_cards.append(
            {
                "day_label": _day_title(day_start.date(), today),
                "date_label": day_start.strftime("%b %d"),
                "segments": day_segments,
                "agenda_items": agenda_items[:6],
            }
        )

    time_slots = [
        {
            "label": time_label(
                local_now.replace(
                    hour=slot_hour,
                    minute=0,
                    second=0,
                    microsecond=0,
                ),
                include_meridiem=True,
            ).replace(":00", ""),
            "top": round((slot_hour / 24) * 100, 2),
        }
        for slot_hour in range(0, 24, 4)
    ]
    return {
        "days": day_cards,
        "time_slots": time_slots,
        "has_blocks": any(day["segments"] for day in day_cards),
    }
