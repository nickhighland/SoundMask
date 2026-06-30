from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.auth import login_required
from app.log_viewer import available_sources, default_source_key, read_log_source

router = APIRouter(prefix="/logs")


@router.get("", response_class=HTMLResponse)
@login_required
async def logs_page(
    request: Request,
    source: str | None = Query(None),
    lines: int = Query(250),
) -> HTMLResponse:
    config = request.app.state.config
    initial_source = source or default_source_key(config)
    return request.app.state.templates.TemplateResponse(
        request,
        "logs.html",
        {
            "log_sources": available_sources(config),
            "log_payload": read_log_source(config, initial_source, lines),
        },
    )


@router.get("/content", response_class=JSONResponse)
@login_required
async def logs_content(
    request: Request,
    source: str = Query("app"),
    lines: int = Query(250),
) -> JSONResponse:
    payload = read_log_source(request.app.state.config, source, lines)
    return JSONResponse(payload)
