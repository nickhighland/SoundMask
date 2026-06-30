from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.audio import AudioManager
from app.auth import has_admin_password, hash_password, verify_password
from app.calendar_client import GoogleCalendarClient, IcsCalendarClient
from app.config import ensure_app_dirs, get_config
from app.db import init_db
from app.routes import (
    calendar_router,
    dashboard_router,
    settings_router,
    sounds_router,
)
from app.scheduler import SoundMaskScheduler


config = get_config()
ensure_app_dirs(config)
templates = Jinja2Templates(directory="app/templates")
database = init_db(config)
audio = AudioManager(config.paths.logs / "mpv.sock")
calendar_client = GoogleCalendarClient(config)
ics_calendar_client = IcsCalendarClient(config)
scheduler = SoundMaskScheduler(database, audio, calendar_client, ics_calendar_client)


@asynccontextmanager
async def lifespan(application: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="SoundMask", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.session_secret,
    https_only=False,
    same_site="lax",
    max_age=60 * 60 * 8,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.state.templates = templates
app.state.db = database
app.state.scheduler = scheduler
app.state.config = config
app.state.audio = audio
app.state.calendar_client = calendar_client
app.state.ics_calendar_client = ics_calendar_client

app.include_router(dashboard_router)
app.include_router(settings_router)
app.include_router(sounds_router)
app.include_router(calendar_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request) -> Response:
    if has_admin_password(request.app.state.db):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"setup_mode": True, "error": None},
    )


@app.post("/setup", response_class=HTMLResponse)
async def setup_password(
    request: Request,
    password: str = Form(...),
    password_confirm: str = Form(...),
) -> Response:
    if has_admin_password(request.app.state.db):
        return RedirectResponse(url="/login", status_code=303)
    if password != password_confirm:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"setup_mode": True, "error": "Passwords did not match."},
            status_code=400,
        )
    request.app.state.db.set_setting(
        "admin_password_hash",
        hash_password(password),
    )
    request.session["authenticated"] = True
    return RedirectResponse(url="/", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> Response:
    if not has_admin_password(request.app.state.db):
        return RedirectResponse(url="/setup", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"setup_mode": False, "error": None},
    )


@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    password: str = Form(...),
) -> Response:
    db = request.app.state.db
    password_hash = db.get_setting("admin_password_hash")
    if not password_hash or not verify_password(password, password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"setup_mode": False, "error": "Invalid password."},
            status_code=400,
        )
    request.session["authenticated"] = True
    return RedirectResponse(url="/", status_code=303)


@app.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
