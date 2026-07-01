from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models import TriggerBlock
from app.routes.dashboard import (
    _normalized_volume_percent,
    build_schedule_view,
    mute_current_session,
    update_volume,
)


def test_build_schedule_view_marks_active_and_upcoming_windows():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    blocks = [
        TriggerBlock(
            start_time=now - timedelta(minutes=15),
            end_time=now + timedelta(minutes=45),
            source="ics_title_match",
        ),
        TriggerBlock(
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=3),
            source="freebusy",
        ),
    ]

    view = build_schedule_view(blocks, now=now)

    assert len(view["entries"]) == 2
    assert view["entries"][0]["active"] is True
    assert view["entries"][0]["source_label"] == "ICS title match"
    assert view["entries"][1]["source_label"] == "Google FreeBusy"
    assert len(view["timeline_segments"]) == 2
    assert 0 <= view["now_percent"] <= 100


def test_dashboard_volume_normalization_clamps_to_supported_range():
    assert _normalized_volume_percent(-5) == 0
    assert _normalized_volume_percent(80) == 80
    assert _normalized_volume_percent(999) == 150


class FakeDashboardDb:
    def __init__(self) -> None:
        self.settings: dict[str, int] = {}

    def set_setting(self, key: str, value: int) -> None:
        self.settings[key] = value


class FakeDashboardAudio:
    def __init__(self, *, playing: bool, backend: str | None) -> None:
        self.playing = playing
        self.backend = backend
        self.volume_updates: list[int] = []
        self.stop_calls = 0

    def is_playing(self) -> bool:
        return self.playing

    def status(self) -> dict[str, str | None]:
        return {"backend": self.backend}

    def set_volume(self, volume_percent: int) -> None:
        self.volume_updates.append(volume_percent)

    def stop(self) -> None:
        self.stop_calls += 1


class FakeDashboardScheduler:
    def __init__(self) -> None:
        self.evaluate_calls = 0
        self.mute_current_session_calls = 0

    def evaluate_playback(self) -> None:
        self.evaluate_calls += 1

    def mute_current_session(self) -> bool:
        self.mute_current_session_calls += 1
        return True


def test_update_volume_returns_json_for_async_dashboard_requests():
    db = FakeDashboardDb()
    audio = FakeDashboardAudio(playing=True, backend="mpv")
    scheduler = FakeDashboardScheduler()
    request = SimpleNamespace(
        headers={
            "accept": "application/json",
            "x-requested-with": "XMLHttpRequest",
        },
        app=SimpleNamespace(
            state=SimpleNamespace(
                db=db,
                audio=audio,
                scheduler=scheduler,
            )
        ),
    )

    response = asyncio.run(
        update_volume.__wrapped__(request=request, volume_percent=120)
    )
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload == {
        "ok": True,
        "volume_percent": 120,
        "playing": True,
        "backend": "mpv",
    }
    assert db.settings["volume_percent"] == 120
    assert audio.volume_updates == [120]
    assert audio.stop_calls == 0
    assert scheduler.evaluate_calls == 0


def test_mute_current_session_redirects_back_to_dashboard():
    scheduler = FakeDashboardScheduler()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                scheduler=scheduler,
            )
        )
    )

    response = asyncio.run(mute_current_session.__wrapped__(request=request))

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert scheduler.mute_current_session_calls == 1
