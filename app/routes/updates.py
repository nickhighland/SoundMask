from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import login_required
from app.update_manager import check_for_updates, load_status, request_install

router = APIRouter(prefix="/updates")


@router.get("", response_class=HTMLResponse)
@login_required
async def updates_page(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "updates.html",
        {
            "update_status": load_status(request.app.state.config),
        },
    )


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
