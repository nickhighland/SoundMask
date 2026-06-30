from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import login_required
from app.models import TitleMatchRule
from app.trigger_rules import regex_error

router = APIRouter(prefix="/calendar")


@router.get("", response_class=HTMLResponse)
@login_required
async def calendar_page(request: Request) -> HTMLResponse:
    db = request.app.state.db
    client = request.app.state.calendar_client
    settings = db.get_settings()
    test_rule_error = None
    if request.query_params.get("regex_error"):
        test_rule_error = request.query_params["regex_error"]
    return request.app.state.templates.TemplateResponse(
        request,
        "calendar.html",
        {
            "settings": settings,
            "connected_account": db.get_calendar_account(),
            "oauth_configured": client.oauth_configured(),
            "saved_calendars": db.list_calendars(),
            "ics_feeds": db.list_ics_feeds(),
            "rules": db.get_title_rules(),
            "status": request.app.state.scheduler.get_status(),
            "regex_error": test_rule_error,
        },
    )


@router.post("/source")
@login_required
async def update_calendar_source(
    request: Request,
    calendar_source: str = Form(...),
) -> RedirectResponse:
    if calendar_source not in {"google", "ics"}:
        calendar_source = "google"
    request.app.state.db.set_setting("calendar_source", calendar_source)
    request.app.state.scheduler.sync_cycle()
    return RedirectResponse(url="/calendar", status_code=303)


@router.get("/oauth/start")
@login_required
async def oauth_start(request: Request) -> RedirectResponse:
    trigger_mode = request.app.state.db.get_setting("trigger_mode", "freebusy")
    redirect_uri = str(request.url_for("oauth_callback"))
    flow = request.app.state.calendar_client.build_flow(redirect_uri, trigger_mode)
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    request.session["oauth_state"] = state
    request.session["oauth_trigger_mode"] = trigger_mode
    return RedirectResponse(url=auth_url, status_code=303)


@router.get("/oauth/callback", name="oauth_callback")
@login_required
async def oauth_callback(request: Request) -> RedirectResponse:
    state = request.session.get("oauth_state")
    trigger_mode = request.session.get("oauth_trigger_mode", "freebusy")
    flow = request.app.state.calendar_client.build_flow(
        str(request.url_for("oauth_callback")),
        trigger_mode,
    )
    flow.fetch_token(
        authorization_response=str(request.url),
        state=state,
    )
    credentials = flow.credentials
    request.app.state.calendar_client.save_credentials(credentials)
    account_email = None
    request.app.state.db.save_calendar_account(
        "google",
        str(request.app.state.calendar_client.token_path),
        account_email,
    )
    return RedirectResponse(url="/calendar", status_code=303)


@router.post("/disconnect")
@login_required
async def disconnect_calendar(request: Request) -> RedirectResponse:
    request.app.state.calendar_client.disconnect()
    request.app.state.db.clear_calendar_account("google")
    return RedirectResponse(url="/calendar", status_code=303)


@router.post("/sync-test")
@login_required
async def sync_test(request: Request) -> RedirectResponse:
    request.app.state.scheduler.sync_cycle()
    return RedirectResponse(url="/calendar", status_code=303)


@router.post("/calendar-id")
@login_required
async def add_calendar_id(
    request: Request,
    calendar_id: str = Form(...),
) -> RedirectResponse:
    request.app.state.db.upsert_calendar(calendar_id.strip(), calendar_id.strip())
    request.app.state.scheduler.sync_cycle()
    return RedirectResponse(url="/calendar", status_code=303)


@router.post("/calendar-toggle")
@login_required
async def toggle_calendar(
    request: Request,
    calendar_id: str = Form(...),
    enabled: str | None = Form(None),
) -> RedirectResponse:
    request.app.state.db.set_calendar_enabled(calendar_id, enabled == "on")
    request.app.state.scheduler.sync_cycle()
    return RedirectResponse(url="/calendar", status_code=303)


@router.post("/discover")
@login_required
async def discover_calendars(request: Request) -> RedirectResponse:
    trigger_mode = request.app.state.db.get_setting("trigger_mode", "freebusy")
    calendars = request.app.state.calendar_client.list_calendars(trigger_mode)
    for item in calendars:
        request.app.state.db.upsert_calendar(
            item["calendar_id"],
            item["display_name"],
            enabled=item.get("primary", False),
        )
    request.app.state.scheduler.sync_cycle()
    return RedirectResponse(url="/calendar", status_code=303)


@router.post("/ics-feeds")
@login_required
async def add_ics_feed(
    request: Request,
    label: str = Form(""),
    location: str = Form(...),
) -> RedirectResponse:
    request.app.state.db.add_ics_feed(label, location)
    request.app.state.scheduler.sync_cycle()
    return RedirectResponse(url="/calendar", status_code=303)


@router.post("/ics-feeds/toggle")
@login_required
async def toggle_ics_feed(
    request: Request,
    feed_id: str = Form(...),
    enabled: str | None = Form(None),
) -> RedirectResponse:
    request.app.state.db.set_ics_feed_enabled(feed_id, enabled == "on")
    request.app.state.scheduler.sync_cycle()
    return RedirectResponse(url="/calendar", status_code=303)


@router.post("/ics-feeds/delete")
@login_required
async def delete_ics_feed(
    request: Request,
    feed_id: str = Form(...),
) -> RedirectResponse:
    request.app.state.db.delete_ics_feed(feed_id)
    request.app.state.scheduler.sync_cycle()
    return RedirectResponse(url="/calendar", status_code=303)


@router.post("/rules")
@login_required
async def add_rule(
    request: Request,
    enabled: str | None = Form(None),
    match_type: str = Form(...),
    match_text: str = Form(...),
    case_sensitive: str | None = Form(None),
    trim_whitespace: str | None = Form(None),
    ignore_cancelled: str | None = Form(None),
    ignore_transparent: str | None = Form(None),
) -> RedirectResponse:
    rule = TitleMatchRule(
        id=None,
        enabled=enabled == "on",
        match_type=match_type,
        match_text=match_text,
        case_sensitive=case_sensitive == "on",
        trim_whitespace=trim_whitespace == "on",
        ignore_cancelled=ignore_cancelled == "on",
        ignore_transparent=ignore_transparent == "on",
    )
    error = regex_error(rule)
    if error:
        return RedirectResponse(
            url=f"/calendar?regex_error={error}",
            status_code=303,
        )
    request.app.state.db.add_title_rule(
        rule.enabled,
        rule.match_type,
        rule.match_text,
        rule.case_sensitive,
        rule.trim_whitespace,
        rule.ignore_cancelled,
        rule.ignore_transparent,
    )
    request.app.state.scheduler.sync_cycle()
    return RedirectResponse(url="/calendar", status_code=303)


@router.post("/rules/delete")
@login_required
async def delete_rule(
    request: Request,
    rule_id: int = Form(...),
) -> RedirectResponse:
    request.app.state.db.delete_title_rule(rule_id)
    request.app.state.scheduler.sync_cycle()
    return RedirectResponse(url="/calendar", status_code=303)
