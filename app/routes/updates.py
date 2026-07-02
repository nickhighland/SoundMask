from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.auth import login_required
from app.display import format_datetime_label
from app.timezones import localize_datetime
from app.update_manager import check_for_updates, load_status, request_install

router = APIRouter(prefix="/updates")


def _update_timestamp_label(
    value: datetime | str | None,
    timezone_name: str | None,
) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return format_datetime_label(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return format_datetime_label(localize_datetime(value, timezone_name))


def _update_status_payload(request: Request) -> dict[str, object]:
    settings = request.app.state.db.get_settings()
    timezone_name = settings.get("timezone_name")
    update_status = load_status(request.app.state.config)
    update_status["last_checked_label"] = _update_timestamp_label(
        update_status.get("last_checked_at"),
        timezone_name,
    )
    update_status["last_install_label"] = _update_timestamp_label(
        update_status.get("last_install_at"),
        timezone_name,
    )
    return update_status


@router.get("", response_class=HTMLResponse)
@login_required
async def updates_page(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "updates.html",
        {
            "update_status": _update_status_payload(request),
        },
    )


@router.get("/status", response_class=JSONResponse)
@login_required
async def updates_status(request: Request) -> JSONResponse:
    return JSONResponse(_update_status_payload(request))


@router.post("/check")
@login_required
async def queue_update_check(request: Request) -> RedirectResponse:
    check_for_updates(request.app.state.config)
    return RedirectResponse(url="/updates", status_code=303)


@router.post("/install")
@login_required
async def queue_update_install(request: Request) -> RedirectResponse:
    request_install(request.app.state.config)
    return RedirectResponse(url="/updates", status_code=303)
