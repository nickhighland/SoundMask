from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.audio import MAX_MPV_VOLUME_PERCENT
from app.auth import login_required
from app.network_config import load_status as load_network_status
from app.network_config import request_port_change

router = APIRouter(prefix="/settings")


def _normalized_volume_percent(raw_value: int) -> int:
    return max(0, min(int(raw_value), MAX_MPV_VOLUME_PERCENT))


def _settings_context(
    request: Request,
    *,
    network_error: str | None = None,
    network_status: dict[str, object] | None = None,
) -> dict[str, object]:
    config = request.app.state.config
    return {
        "settings": request.app.state.db.get_settings(),
        "network_supported": config.is_production,
        "network_error": network_error,
        "network_status": network_status or load_network_status(config),
    }


@router.get("", response_class=HTMLResponse)
@login_required
async def settings_page(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "settings.html",
        _settings_context(request),
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
    db.set_setting("volume_percent", _normalized_volume_percent(volume_percent))
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


@router.post("/network", response_class=HTMLResponse)
@login_required
async def update_network_settings(
    request: Request,
    port: int = Form(...),
) -> HTMLResponse:
    config = request.app.state.config
    if not config.is_production:
        return request.app.state.templates.TemplateResponse(
            request,
            "settings.html",
            _settings_context(
                request,
                network_error=(
                    "In-app port changes are only available on Linux appliance installs."
                ),
            ),
            status_code=400,
        )
    try:
        network_status = request_port_change(config, port)
    except ValueError as exc:
        return request.app.state.templates.TemplateResponse(
            request,
            "settings.html",
            _settings_context(request, network_error=str(exc)),
            status_code=400,
        )
    if not network_status["request_pending"]:
        return request.app.state.templates.TemplateResponse(
            request,
            "settings.html",
            _settings_context(request, network_status=network_status),
        )
    return request.app.state.templates.TemplateResponse(
        request,
        "network_change_requested.html",
        {"network_status": network_status},
        status_code=202,
    )
