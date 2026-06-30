from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.auth import login_required

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac"}

router = APIRouter(prefix="/sounds")


def _safe_filename(raw_name: str) -> str:
    name = Path(raw_name).name
    return "".join(char for char in name if char.isalnum() or char in {"-", "_", ".", " "}).strip()


@router.get("", response_class=HTMLResponse)
@login_required
async def sounds_page(request: Request) -> HTMLResponse:
    db = request.app.state.db
    audio = request.app.state.audio
    return request.app.state.templates.TemplateResponse(
        request,
        "sounds.html",
        {
            "sounds": db.list_sounds(),
            "active_sound": db.get_active_sound(),
            "volume_percent": db.get_setting("volume_percent", 35),
            "audio_status": audio.status(),
            "audio_diagnostics": audio.diagnostics(),
            "sound_message": request.session.pop("sound_message", None),
        },
    )


@router.post("/upload")
@login_required
async def upload_sound(
    request: Request,
    sound_file: UploadFile = File(...),
) -> RedirectResponse:
    filename = _safe_filename(sound_file.filename or "")
    extension = Path(filename).suffix.lower()
    if not filename or extension not in ALLOWED_EXTENSIONS:
        request.session["sound_message"] = "Upload a WAV, MP3, OGG, or FLAC file."
        return RedirectResponse(url="/sounds", status_code=303)
    target = request.app.state.config.paths.sounds / filename
    target.write_bytes(await sound_file.read())
    mime_type = sound_file.content_type or mimetypes.guess_type(filename)[0]
    request.app.state.db.add_sound(filename, filename, str(target), mime_type)
    if request.app.state.db.get_active_sound() is None:
        sounds = request.app.state.db.list_sounds()
        if sounds:
            request.app.state.db.set_active_sound(sounds[0].id)
    request.session["sound_message"] = f"Uploaded {filename}."
    return RedirectResponse(url="/sounds", status_code=303)


@router.post("/select")
@login_required
async def select_sound(
    request: Request,
    sound_id: int = Form(...),
) -> RedirectResponse:
    request.app.state.db.set_active_sound(sound_id)
    request.app.state.scheduler.evaluate_playback()
    sound = request.app.state.db.get_sound(sound_id)
    request.session["sound_message"] = (
        f"{sound.display_name} is now the active masking track."
        if sound
        else "Active sound updated."
    )
    return RedirectResponse(url="/sounds", status_code=303)


@router.post("/test")
@login_required
async def test_sound(
    request: Request,
    sound_id: int = Form(...),
) -> RedirectResponse:
    sound = request.app.state.db.get_sound(sound_id)
    if sound and sound.path.exists():
        result = request.app.state.audio.test(
            sound.path,
            int(request.app.state.db.get_setting("volume_percent", 35)),
        )
        request.session["sound_message"] = str(result["message"])
    else:
        request.session["sound_message"] = "That sound file is missing from disk."
    return RedirectResponse(url="/sounds", status_code=303)


@router.get("/{sound_id}/preview")
@login_required
async def preview_sound(
    request: Request,
    sound_id: int,
) -> FileResponse:
    sound = request.app.state.db.get_sound(sound_id)
    if sound is None or not sound.path.exists():
        raise HTTPException(status_code=404, detail="Sound not found.")
    return FileResponse(
        sound.path,
        media_type=sound.mime_type or mimetypes.guess_type(sound.path.name)[0] or "application/octet-stream",
        filename=sound.filename,
    )


@router.post("/delete")
@login_required
async def delete_sound(
    request: Request,
    sound_id: int = Form(...),
) -> RedirectResponse:
    sound = request.app.state.db.delete_sound(sound_id)
    if sound and sound.path.exists():
        sound.path.unlink(missing_ok=True)
    remaining = request.app.state.db.list_sounds()
    if remaining and not any(item.is_active for item in remaining):
        request.app.state.db.set_active_sound(remaining[0].id)
    request.app.state.scheduler.evaluate_playback()
    request.session["sound_message"] = (
        f"Deleted {sound.display_name}."
        if sound
        else "Sound removed."
    )
    return RedirectResponse(url="/sounds", status_code=303)
