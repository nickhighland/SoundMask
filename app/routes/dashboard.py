from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.audio import DEFAULT_VOLUME_PERCENT, MAX_MPV_VOLUME_PERCENT
from app.auth import login_required
from app.dashboard_health import build_dashboard_health
from app.display import format_datetime_label
from app.schedule_views import build_schedule_view
from app.timezones import localize_datetime

router = APIRouter()


def _normalized_volume_percent(raw_value: int) -> int:
    return max(0, min(int(raw_value), MAX_MPV_VOLUME_PERCENT))


def _request_prefers_json(request: Request) -> bool:
    accept_header = request.headers.get("accept", "")
    requested_with = request.headers.get("x-requested-with", "")
    return (
        "application/json" in accept_header.lower()
        or requested_with.lower() == "xmlhttprequest"
    )


@router.get("/", response_class=HTMLResponse)
@login_required
async def dashboard(request: Request) -> HTMLResponse:
    db = request.app.state.db
    scheduler = request.app.state.scheduler
    settings = db.get_settings()
    timezone_name = settings.get("timezone_name")
    audio = request.app.state.audio
    status = scheduler.get_status()
    current_datetime_label = format_datetime_label(
        localize_datetime(datetime.now(timezone.utc), timezone_name)
    )
    next_block_label = None
    if status["next_block"]:
        next_start = localize_datetime(status["next_block"].start_time, timezone_name)
        next_block_label = format_datetime_label(next_start)
    can_mute_current_session = scheduler.current_session_mute_until() is not None
    return request.app.state.templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "settings": settings,
            "status": status,
            "current_datetime_label": current_datetime_label,
            "next_block_label": next_block_label,
            "can_mute_current_session": can_mute_current_session,
            "schedule_view": build_schedule_view(
                list(scheduler.current_blocks),
                timezone_name=timezone_name,
            ),
            "fake_blocks": db.get_state("fake_blocks", []),
            "audio_status": audio.status(),
            "audio_diagnostics": audio.diagnostics(),
            "health_summary": build_dashboard_health(
                request.app.state.config,
                scheduler,
                audio,
                timezone_name=timezone_name,
            ),
            "max_volume_percent": MAX_MPV_VOLUME_PERCENT,
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


@router.post("/actions/mute-current-session")
@login_required
async def mute_current_session(request: Request) -> RedirectResponse:
    request.app.state.scheduler.mute_current_session()
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
    mix_layers = db.resolve_sound_mix_layers()
    sound_source = None
    if mix_layers:
        try:
            sound_source = request.app.state.sound_mixer.playback_source(mix_layers)
            request.app.state.audio.clear_error()
        except RuntimeError as exc:
            request.app.state.audio.report_error(str(exc))
    if sound_source and sound_source.exists():
        request.app.state.audio.test(
            sound_source,
            int(db.get_setting("volume_percent", DEFAULT_VOLUME_PERCENT)),
        )
    return RedirectResponse(url="/", status_code=303)


@router.post("/actions/volume")
@login_required
async def update_volume(
    request: Request,
    volume_percent: int = Form(...),
) -> Response:
    db = request.app.state.db
    normalized_volume = _normalized_volume_percent(volume_percent)
    db.set_setting("volume_percent", normalized_volume)

    audio = request.app.state.audio
    if audio.is_playing():
        if audio.status().get("backend") == "mpv":
            audio.set_volume(normalized_volume)
        else:
            audio.stop()
            request.app.state.scheduler.evaluate_playback()

    if _request_prefers_json(request):
        return JSONResponse(
            {
                "ok": True,
                "volume_percent": normalized_volume,
                "playing": audio.is_playing(),
                "backend": audio.status().get("backend"),
            }
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
