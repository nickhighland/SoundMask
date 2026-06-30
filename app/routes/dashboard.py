from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import login_required
from app.schedule_views import build_schedule_view

router = APIRouter()


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
