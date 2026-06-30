from __future__ import annotations

from datetime import datetime, timezone

from app.models import TriggerBlock
from app.models import TitleMatchRule
from app.trigger_rules import matches_title, merge_blocks, regex_error


def make_rule(**overrides):
    values = {
        "id": 1,
        "enabled": True,
        "match_type": "exact",
        "match_text": "Counseling appointment",
        "case_sensitive": False,
        "trim_whitespace": True,
        "ignore_cancelled": True,
        "ignore_transparent": True,
    }
    values.update(overrides)
    return TitleMatchRule(**values)


def test_exact_match():
    assert matches_title("Counseling appointment", make_rule())


def test_case_insensitive_exact_match():
    assert matches_title("counseling appointment", make_rule())


def test_contains_match():
    assert matches_title(
        "Weekly Counseling appointment with buffer",
        make_rule(match_type="contains", match_text="Counseling"),
    )


def test_starts_with_match():
    assert matches_title(
        "Counseling appointment follow-up",
        make_rule(match_type="starts_with", match_text="Counseling"),
    )


def test_ends_with_match():
    assert matches_title(
        "Primary Counseling appointment",
        make_rule(match_type="ends_with", match_text="appointment"),
    )


def test_regex_match():
    assert matches_title(
        "Counseling appointment 101",
        make_rule(match_type="regex", match_text=r"^Counseling appointment\b"),
    )


def test_invalid_regex_is_safe():
    rule = make_rule(match_type="regex", match_text="(")
    assert matches_title("Counseling appointment", rule) is False
    assert regex_error(rule)


def test_whitespace_trimming():
    assert matches_title(
        " Counseling appointment ",
        make_rule(match_text=" Counseling appointment "),
    )


def test_merge_blocks_does_not_mutate_input_blocks():
    blocks = [
        TriggerBlock(
            start_time=datetime(2026, 6, 30, 18, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 30, 19, 0, tzinfo=timezone.utc),
            source="ics_title_match",
        ),
        TriggerBlock(
            start_time=datetime(2026, 6, 30, 19, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 6, 30, 20, 0, tzinfo=timezone.utc),
            source="ics_title_match",
        ),
    ]

    merged = merge_blocks(blocks)

    assert len(merged) == 1
    assert merged[0].start_time == datetime(2026, 6, 30, 18, 0, tzinfo=timezone.utc)
    assert merged[0].end_time == datetime(2026, 6, 30, 20, 0, tzinfo=timezone.utc)
    assert blocks[0].end_time == datetime(2026, 6, 30, 19, 0, tzinfo=timezone.utc)
    assert blocks[1].end_time == datetime(2026, 6, 30, 20, 0, tzinfo=timezone.utc)
