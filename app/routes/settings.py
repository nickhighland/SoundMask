from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import login_required

router = APIRouter(prefix="/settings")


@router.get("", response_class=HTMLResponse)
@login_required
async def settings_page(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "settings.html",
        {"settings": request.app.state.db.get_settings()},
    )


@router.post("")
@login_required
async def update_settings(
    request: Request,
    trigger_mode: str = Form(...),
    calendar_sync_interval_seconds: int = Form(...),
    start_buffer_minutes: int = Form(...),
    end_buffer_minutes: int = Form(...),
    active_hours_enabled: str | None = Form(None),
    active_hours_start: str = Form(...),
    active_hours_end: str = Form(...),
    max_event_duration_minutes: int = Form(...),
    ignore_all_day_events: str | None = Form(None),
    volume_percent: int = Form(...),
    fade_in_seconds: int = Form(...),
    fade_out_seconds: int = Form(...),
    manual_play_duration_minutes: int = Form(...),
    debug_store_event_summaries: str | None = Form(None),
) -> RedirectResponse:
    db = request.app.state.db
    db.set_setting("trigger_mode", trigger_mode)
    db.set_setting(
        "calendar_sync_interval_seconds",
        calendar_sync_interval_seconds,
    )
    db.set_setting("start_buffer_minutes", start_buffer_minutes)
    db.set_setting("end_buffer_minutes", end_buffer_minutes)
    db.set_setting("active_hours_enabled", active_hours_enabled == "on")
    db.set_setting("active_hours_start", active_hours_start)
    db.set_setting("active_hours_end", active_hours_end)
    db.set_setting("max_event_duration_minutes", max_event_duration_minutes)
    db.set_setting("ignore_all_day_events", ignore_all_day_events == "on")
    db.set_setting("volume_percent", volume_percent)
    db.set_setting("fade_in_seconds", fade_in_seconds)
    db.set_setting("fade_out_seconds", fade_out_seconds)
    db.set_setting(
        "manual_play_duration_minutes",
        manual_play_duration_minutes,
    )
    db.set_setting(
        "debug_store_event_summaries",
        debug_store_event_summaries == "on",
    )
    request.app.state.scheduler.reload_jobs()
    request.app.state.scheduler.evaluate_playback()
    return RedirectResponse(url="/settings", status_code=303)