from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth import login_required
from app.schedule_views import build_calendar_view

router = APIRouter(prefix="/calendar-view")


@router.get("", response_class=HTMLResponse)
@login_required
async def calendar_view_page(request: Request) -> HTMLResponse:
    scheduler = request.app.state.scheduler
    settings = request.app.state.db.get_settings()
    return request.app.state.templates.TemplateResponse(
        request,
        "calendar_view.html",
        {
            "calendar_view": build_calendar_view(
                list(scheduler.calendar_blocks),
                timezone_name=settings.get("timezone_name"),
            ),
            "status": scheduler.get_status(),
        },
    )
