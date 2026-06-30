from __future__ import annotations

from datetime import datetime, timezone

from app.models import TriggerBlock
from app.trigger_rules import apply_buffers, merge_blocks


def make_block(start_hour: int, start_minute: int, end_hour: int, end_minute: int):
    return TriggerBlock(
        start_time=datetime(2026, 1, 1, start_hour, start_minute, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, end_hour, end_minute, tzinfo=timezone.utc),
    )


def test_merge_blocks_merges_overlap():
    blocks = [make_block(14, 0, 14, 53), make_block(14, 45, 15, 30)]
    merged = merge_blocks(blocks)
    assert len(merged) == 1
    assert merged[0].start_time.hour == 14
    assert merged[0].end_time.hour == 15
    assert merged[0].end_time.minute == 30


def test_apply_buffers_extends_range():
    buffered = apply_buffers([make_block(14, 0, 14, 53)], 2, 3)
    assert buffered[0].start_time.minute == 58
    assert buffered[0].start_time.hour == 13
    assert buffered[0].end_time.hour == 14
    assert buffered[0].end_time.minute == 56