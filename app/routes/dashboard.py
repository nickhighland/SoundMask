from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import login_required
from app.models import TriggerBlock

router = APIRouter()


def _source_label(source: str) -> str:
    labels = {
        "fake": "Fake mode",
        "freebusy": "Google FreeBusy",
        "title_match": "Google title match",
        "ics_freebusy": "ICS busy window",
        "ics_title_match": "ICS title match",
    }
    return labels.get(source, source.replace("_", " ").title())


def _time_label(value: datetime, include_meridiem: bool = True) -> str:
    pattern = "%I:%M %p" if include_meridiem else "%I:%M"
    return value.strftime(pattern).lstrip("0")


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
                "start_label": _time_label(start_local),
                "end_label": _time_label(end_local),
                "day_label": day_name,
                "duration_label": f"{duration_minutes} min",
                "source_label": _source_label(block.source),
                "active": active,
            }
        )

        clip_start = max(start_local, day_start)
        clip_end = min(end_local, day_end)
        if clip_end <= clip_start:
            continue
        left = (
            (clip_start - day_start).total_seconds() / day_span_seconds
        ) * 100
        width = max(
            2,
            ((clip_end - clip_start).total_seconds() / day_span_seconds) * 100,
        )
        timeline_segments.append(
            {
                "left": round(left, 2),
                "width": round(width, 2),
                "label": f"{_time_label(start_local, include_meridiem=False)}-{_time_label(end_local)}",
                "active": active,
                "source_label": _source_label(block.source),
            }
        )

    timeline_hours = [
        _time_label(day_start + timedelta(hours=hour)).replace(":00", "")
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
        "now_label": _time_label(local_now),
    }


@router.get("/", response_class=HTMLResponse)
@login_required
async def dashboard(request: Request) -> HTMLResponse:
    db = request.app.state.db
    scheduler = request.app.state.scheduler
    settings = db.get_settings()
    audio = request.app.state.audio
    return request.app.state.templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "settings": settings,
            "status": scheduler.get_status(),
            "schedule_view": build_schedule_view(list(scheduler.current_blocks)),
            "fake_blocks": db.get_state("fake_blocks", []),
            "audio_status": audio.status(),
            "audio_diagnostics": audio.diagnostics(),
        },
    )


@router.post("/actions/manual-play")
@login_required
async def manual_play(request: Request) -> RedirectResponse:
    request.app.state.scheduler.manual_play()
    return RedirectResponse(url="/", status_code=303)


@router.post("/actions/manual-stop")
@login_required
async def manual_stop(request: Request) -> RedirectResponse:
    request.app.state.scheduler.manual_stop()
    return RedirectResponse(url="/", status_code=303)


@router.post("/actions/mute")
@login_required
async def mute(request: Request, minutes: int = Form(30)) -> RedirectResponse:
    request.app.state.scheduler.mute_for(minutes)
    return RedirectResponse(url="/", status_code=303)


@router.post("/actions/unmute")
@login_required
async def unmute(request: Request) -> RedirectResponse:
    request.app.state.scheduler.clear_mute()
    return RedirectResponse(url="/", status_code=303)


@router.post("/actions/test-sound")
@login_required
async def test_sound(request: Request) -> RedirectResponse:
    db = request.app.state.db
    sound = db.get_active_sound()
    if sound and sound.path.exists():
        request.app.state.audio.test(
            sound.path,
            int(db.get_setting("volume_percent", 35)),
        )
    return RedirectResponse(url="/", status_code=303)


@router.post("/actions/fake-block")
@login_required
async def create_fake_block(
    request: Request,
    start_in_minutes: int = Form(1),
    duration_minutes: int = Form(2),
) -> RedirectResponse:
    request.app.state.scheduler.add_fake_block(start_in_minutes, duration_minutes)
    return RedirectResponse(url="/", status_code=303)


@router.post("/actions/fake-blocks/clear")
@login_required
async def clear_fake_blocks(request: Request) -> RedirectResponse:
    request.app.state.scheduler.clear_fake_blocks()
    return RedirectResponse(url="/", status_code=303)
