from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import ManualState, TriggerBlock
from app.trigger_rules import should_play


def base_settings():
    return {
        "active_hours_enabled": True,
        "active_hours_start": "07:00",
        "active_hours_end": "21:00",
    }


def test_manual_play_overrides_calendar():
    now = datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc)
    state = ManualState(manual_play_until=now + timedelta(minutes=10))
    decision = should_play(now, base_settings(), [], state)
    assert decision.should_play is True
    assert decision.reason == "manual"


def test_mute_blocks_playback():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    block = TriggerBlock(now - timedelta(minutes=1), now + timedelta(minutes=1))
    state = ManualState(mute_until=now + timedelta(minutes=10))
    decision = should_play(now, base_settings(), [block], state)
    assert decision.should_play is False
    assert decision.reason == "muted"


def test_calendar_block_triggers_playback():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    block = TriggerBlock(now - timedelta(minutes=1), now + timedelta(minutes=1))
    decision = should_play(now, base_settings(), [block], ManualState())
    assert decision.should_play is True
    assert decision.reason == "calendar_active"