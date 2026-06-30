from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.models import TriggerBlock

CALENDAR_DEFAULT_START_HOUR = 8
CALENDAR_DEFAULT_END_HOUR = 22
CALENDAR_HOUR_HEIGHT_PX = 80


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


def appointment_label(source: str) -> str:
    if source == "fake":
        return "Fake appointment"
    return "Counseling appointment"


def appointment_start(block: TriggerBlock) -> datetime:
    return block.display_start_time or block.start_time


def appointment_end(block: TriggerBlock) -> datetime:
    return block.display_end_time or block.end_time


def compact_time_label(value: datetime, include_meridiem: bool = True) -> str:
    base = value.strftime("%I:%M").lstrip("0")
    if base.endswith(":00"):
        base = base[:-3]
    if not include_meridiem:
        return base
    return f"{base}{value.strftime('%p').lower()}"


def appointment_time_range_label(start: datetime, end: datetime) -> str:
    same_meridiem = start.strftime("%p") == end.strftime("%p")
    return (
        f"{compact_time_label(start, include_meridiem=not same_meridiem)} - "
        f"{compact_time_label(end)}"
    )


def timezone_label(value: datetime) -> str:
    offset = value.utcoffset() or timedelta()
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    if minutes:
        return f"GMT{sign}{hours:02d}:{minutes:02d}"
    return f"GMT{sign}{hours:02d}"


def _layout_day_events(
    raw_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not raw_events:
        return []

    events = sorted(
        raw_events,
        key=lambda item: (
            item["start_local"],
            item["end_local"],
            item["title_label"],
        ),
    )
    laid_out: list[dict[str, Any]] = []
    cluster: list[dict[str, Any]] = []
    cluster_end: datetime | None = None

    def flush_cluster(cluster_events: list[dict[str, Any]]) -> None:
        if not cluster_events:
            return

        column_ends: list[datetime] = []
        for event in cluster_events:
            start_local = event["start_local"]
            end_local = event["end_local"]
            column_index: int | None = None
            for index, column_end in enumerate(column_ends):
                if column_end <= start_local:
                    column_index = index
                    column_ends[index] = end_local
                    break
            if column_index is None:
                column_index = len(column_ends)
                column_ends.append(end_local)
            event["column_index"] = column_index

        column_count = max(1, len(column_ends))
        width_percent = 100 / column_count
        for event in cluster_events:
            event["left_percent"] = round(event["column_index"] * width_percent, 3)
            event["width_percent"] = round(width_percent, 3)
            laid_out.append(event)

    for event in events:
        start_local = event["start_local"]
        end_local = event["end_local"]
        if cluster_end is None or start_local < cluster_end:
            cluster.append(event)
            cluster_end = (
                end_local if cluster_end is None else max(cluster_end, end_local)
            )
            continue
        flush_cluster(cluster)
        cluster = [event]
        cluster_end = end_local

    flush_cluster(cluster)
    return laid_out


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
    start_of_today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    visible_window_end = start_of_today + timedelta(days=days)
    visible_blocks = [
        block
        for block in sorted(blocks, key=appointment_start)
        if (
            appointment_end(block).astimezone(local_tz) > start_of_today
            and appointment_start(block).astimezone(local_tz) < visible_window_end
        )
    ]

    earliest_hour = min(
        (
            appointment_start(block).astimezone(local_tz).hour
            for block in visible_blocks
        ),
        default=CALENDAR_DEFAULT_START_HOUR,
    )
    latest_end = max(
        (
            appointment_end(block).astimezone(local_tz)
            for block in visible_blocks
        ),
        default=start_of_today.replace(hour=CALENDAR_DEFAULT_END_HOUR),
    )
    latest_hour = latest_end.hour + (1 if latest_end.minute or latest_end.second else 0)
    visible_start_hour = min(CALENDAR_DEFAULT_START_HOUR, earliest_hour)
    visible_end_hour = max(CALENDAR_DEFAULT_END_HOUR, latest_hour)
    visible_end_hour = min(24, max(visible_start_hour + 8, visible_end_hour))
    grid_height = (visible_end_hour - visible_start_hour) * CALENDAR_HOUR_HEIGHT_PX

    day_cards: list[dict[str, Any]] = []
    for offset in range(days):
        day_start = start_of_today + timedelta(days=offset)
        visible_day_start = day_start.replace(
            hour=visible_start_hour,
            minute=0,
            second=0,
            microsecond=0,
        )
        visible_grid_end = visible_day_start + timedelta(
            hours=visible_end_hour - visible_start_hour
        )
        raw_events: list[dict[str, Any]] = []

        for block in visible_blocks:
            start_local = appointment_start(block).astimezone(local_tz)
            end_local = appointment_end(block).astimezone(local_tz)
            if end_local <= visible_day_start or start_local >= visible_grid_end:
                continue

            clip_start = max(start_local, visible_day_start)
            clip_end = min(end_local, visible_grid_end)
            top_px = int(
                ((clip_start - visible_day_start).total_seconds() / 3600)
                * CALENDAR_HOUR_HEIGHT_PX
            )
            height_px = max(
                22,
                int(
                    ((clip_end - clip_start).total_seconds() / 3600)
                    * CALENDAR_HOUR_HEIGHT_PX
                )
                - 2,
            )
            active = appointment_start(block) <= current_time <= appointment_end(block)
            raw_events.append(
                {
                    "start_local": clip_start,
                    "end_local": clip_end,
                    "top_px": top_px,
                    "height_px": height_px,
                    "title_label": appointment_label(block.source),
                    "time_label": appointment_time_range_label(start_local, end_local),
                    "active": active,
                    "compact": height_px < 54,
                }
            )

        day_events = _layout_day_events(raw_events)

        day_cards.append(
            {
                "day_label": day_start.strftime("%a").upper(),
                "day_number": day_start.day,
                "date_label": day_start.strftime("%b %d"),
                "is_today": day_start.date() == local_now.date(),
                "events": day_events,
            }
        )

    time_slots = [
        {
            "label": time_label(
                start_of_today.replace(
                    hour=slot_hour % 24,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            ).replace(":00", ""),
            "top_px": (slot_hour - visible_start_hour) * CALENDAR_HOUR_HEIGHT_PX,
        }
        for slot_hour in range(visible_start_hour, visible_end_hour + 1)
    ]
    return {
        "days": day_cards,
        "time_slots": time_slots,
        "has_blocks": any(day["events"] for day in day_cards),
        "grid_height": grid_height,
        "timezone_label": timezone_label(local_now),
    }
