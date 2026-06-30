from __future__ import annotations

import re
from dataclasses import replace
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from app.models import ManualState, TitleMatchRule, TriggerBlock


@dataclass(slots=True)
class PlaybackDecision:
    should_play: bool
    reason: str


def merge_blocks(blocks: list[TriggerBlock]) -> list[TriggerBlock]:
    if not blocks:
        return []
    ordered = sorted(blocks, key=lambda block: block.start_time)
    merged = [replace(ordered[0])]
    for current in ordered[1:]:
        previous = merged[-1]
        if current.start_time <= previous.end_time:
            previous.end_time = max(previous.end_time, current.end_time)
            continue
        merged.append(replace(current))
    return merged


def apply_buffers(blocks: list[TriggerBlock], start_buffer: int, end_buffer: int) -> list[TriggerBlock]:
    buffered: list[TriggerBlock] = []
    for block in blocks:
        buffered.append(
            TriggerBlock(
                start_time=block.start_time - timedelta(minutes=start_buffer),
                end_time=block.end_time + timedelta(minutes=end_buffer),
                display_start_time=block.display_start_time or block.start_time,
                display_end_time=block.display_end_time or block.end_time,
                source=block.source,
                is_all_day=block.is_all_day,
                calendar_id=block.calendar_id,
                event_id_hash=block.event_id_hash,
                summary_hash=block.summary_hash,
                matched_rule_id=block.matched_rule_id,
            )
        )
    return merge_blocks(buffered)


def is_now_in_active_block(now: datetime, blocks: list[TriggerBlock]) -> bool:
    return any(block.start_time <= now <= block.end_time for block in blocks)


def get_next_block(now: datetime, blocks: list[TriggerBlock]) -> TriggerBlock | None:
    future_blocks = [block for block in blocks if block.start_time > now]
    return min(future_blocks, key=lambda block: block.start_time) if future_blocks else None


def _within_active_hours(now: datetime, settings: dict[str, object]) -> bool:
    if not settings.get("active_hours_enabled", True):
        return True
    start_value = time.fromisoformat(str(settings.get("active_hours_start", "07:00")))
    end_value = time.fromisoformat(str(settings.get("active_hours_end", "21:00")))
    current = now.timetz().replace(tzinfo=None)
    if start_value <= end_value:
        return start_value <= current <= end_value
    return current >= start_value or current <= end_value


def should_play(
    now: datetime,
    settings: dict[str, object],
    blocks: list[TriggerBlock],
    manual_state: ManualState,
) -> PlaybackDecision:
    if manual_state.mute_until and now < manual_state.mute_until:
        return PlaybackDecision(False, "muted")
    if manual_state.manual_play_until and now < manual_state.manual_play_until:
        return PlaybackDecision(True, "manual")
    if not _within_active_hours(now, settings):
        return PlaybackDecision(False, "outside_active_hours")
    if is_now_in_active_block(now, blocks):
        return PlaybackDecision(True, "calendar_active")
    return PlaybackDecision(False, "idle")


def matches_title(summary: str, rule: TitleMatchRule) -> bool:
    if not rule.enabled:
        return False
    candidate = summary
    pattern = rule.match_text
    if rule.trim_whitespace:
        candidate = candidate.strip()
        pattern = pattern.strip()
    if not rule.case_sensitive:
        candidate = candidate.lower()
        pattern = pattern.lower()
    if rule.match_type == "exact":
        return candidate == pattern
    if rule.match_type == "contains":
        return pattern in candidate
    if rule.match_type == "starts_with":
        return candidate.startswith(pattern)
    if rule.match_type == "ends_with":
        return candidate.endswith(pattern)
    if rule.match_type == "regex":
        try:
            flags = 0 if rule.case_sensitive else re.IGNORECASE
            raw_pattern = rule.match_text.strip() if rule.trim_whitespace else rule.match_text
            return re.search(raw_pattern, summary, flags=flags) is not None
        except re.error:
            return False
    return False


def regex_error(rule: TitleMatchRule) -> str | None:
    if rule.match_type != "regex":
        return None
    pattern = rule.match_text.strip() if rule.trim_whitespace else rule.match_text
    try:
        re.compile(pattern)
    except re.error as exc:
        return str(exc)
    return None
