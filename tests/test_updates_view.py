from __future__ import annotations

from app.routes.updates import _update_timestamp_label


def test_update_timestamp_label_localizes_utc_iso_strings() -> None:
    assert (
        _update_timestamp_label(
            "2026-07-01T17:00:00+00:00",
            "America/New_York",
        )
        == "July 1, 2026 at 1:00 PM"
    )


def test_update_timestamp_label_keeps_invalid_strings_readable() -> None:
    assert _update_timestamp_label("Not available yet", "America/New_York") == "Not available yet"
