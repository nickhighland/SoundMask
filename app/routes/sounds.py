from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.audio import DEFAULT_VOLUME_PERCENT, MAX_MPV_VOLUME_PERCENT
from app.auth import login_required
from app.bundled_sounds import bundled_sounds_dir
from app.models import SoundMixLayer, SoundRecord

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac"}
SOUND_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Noise", ("white noise", "brown noise", "pink noise", "noise")),
    ("Nature", ("birds", "insects", "serengeti", "wind farm", "wind", "campfire")),
    ("Water", ("rain", "stream", "waterfall", "waves", "river", "creek")),
    ("Weather", ("thunderstorm", "storm")),
    (
        "City & Indoor",
        (
            "highway",
            "city square",
            "crowded cafeteria",
            "restaurant ambience",
            "time square",
            "typing",
        ),
    ),
    ("Travel & Transit", ("train",)),
)
SOUND_CATEGORY_ORDER: tuple[str, ...] = (
    *(label for label, _keywords in SOUND_CATEGORY_RULES),
    "Custom Uploads",
    "Library",
)

router = APIRouter(prefix="/sounds")


def _safe_filename(raw_name: str) -> str:
    name = Path(raw_name).name
    return "".join(char for char in name if char.isalnum() or char in {"-", "_", ".", " "}).strip()


def _normalized_layer_volume(raw_value: object) -> int:
    try:
        return max(0, min(int(raw_value), 100))
    except (TypeError, ValueError):
        return 100


def _bundled_sound_filenames() -> set[str]:
    source_dir = bundled_sounds_dir()
    if not source_dir.exists():
        return set()
    return {path.name for path in source_dir.glob("*") if path.is_file()}


def _sound_category_name(sound: SoundRecord, bundled_filenames: set[str]) -> str:
    if sound.filename not in bundled_filenames:
        return "Custom Uploads"

    normalized_name = sound.display_name.lower()
    for label, keywords in SOUND_CATEGORY_RULES:
        if any(keyword in normalized_name for keyword in keywords):
            return label
    return "Library"


def _group_sounds_by_category(
    sounds: list[SoundRecord],
    bundled_filenames: set[str],
) -> list[tuple[str, list[SoundRecord]]]:
    grouped: dict[str, list[SoundRecord]] = {
        label: [] for label in SOUND_CATEGORY_ORDER
    }
    for sound in sounds:
        grouped.setdefault(
            _sound_category_name(sound, bundled_filenames),
            [],
        ).append(sound)
    return [
        (label, grouped[label])
        for label in SOUND_CATEGORY_ORDER
        if grouped.get(label)
    ]


@router.get("", response_class=HTMLResponse)
@login_required
async def sounds_page(request: Request) -> HTMLResponse:
    db = request.app.state.db
    audio = request.app.state.audio
    sounds = db.list_sounds()
    mix_layers = db.resolve_sound_mix_layers()
    mix_diagnostics = request.app.state.sound_mixer.diagnostics()
    bundled_sound_filenames = _bundled_sound_filenames()
    return request.app.state.templates.TemplateResponse(
        request,
        "sounds.html",
        {
            "sounds": sounds,
            "sound_categories": _group_sounds_by_category(
                sounds,
                bundled_sound_filenames,
            ),
            "bundled_sound_filenames": bundled_sound_filenames,
            "mix_layers": mix_layers,
            "mix_layer_map": {
                layer.sound.id: layer.volume_percent for layer in mix_layers
            },
            "mix_summary": request.app.state.sound_mixer.describe_layers(mix_layers),
            "mix_diagnostics": mix_diagnostics,
            "selected_layer_count": len(mix_layers),
            "volume_percent": db.get_setting(
                "volume_percent",
                DEFAULT_VOLUME_PERCENT,
            ),
            "max_volume_percent": MAX_MPV_VOLUME_PERCENT,
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
    sound = request.app.state.db.add_sound(
        filename,
        Path(filename).stem,
        str(target),
        mime_type,
    )
    if request.app.state.db.get_active_sound() is None:
        request.app.state.db.set_active_sound(sound.id)
    request.session["sound_message"] = f"Uploaded {filename}."
    return RedirectResponse(url="/sounds", status_code=303)


@router.post("/mix")
@login_required
async def update_mix(
    request: Request,
) -> RedirectResponse:
    db = request.app.state.db
    form = await request.form()
    available_sounds = {sound.id: sound for sound in db.list_sounds()}
    selected_sound_ids: list[int] = []
    for raw_value in form.getlist("selected_sound_ids"):
        try:
            sound_id = int(raw_value)
        except (TypeError, ValueError):
            continue
        if sound_id not in available_sounds or sound_id in selected_sound_ids:
            continue
        selected_sound_ids.append(sound_id)

    layers = [
        SoundMixLayer(
            sound_id=sound_id,
            volume_percent=_normalized_layer_volume(
                form.get(f"layer_volume_{sound_id}", 100)
            ),
        )
        for sound_id in selected_sound_ids
    ]
    db.set_sound_mix_layers(layers)
    if len(layers) == 1:
        db.set_active_sound(layers[0].sound_id)

    audio = request.app.state.audio
    audio.clear_error()
    message = "Cleared the current mix."
    if layers:
        try:
            request.app.state.sound_mixer.playback_source(db.resolve_sound_mix_layers())
            message = f"Saved a mix with {len(layers)} layer(s)."
        except RuntimeError as exc:
            audio.report_error(str(exc))
            message = f"Saved a mix with {len(layers)} layer(s). {exc}"
    request.app.state.scheduler.evaluate_playback()
    request.session["sound_message"] = message
    return RedirectResponse(url="/sounds", status_code=303)


@router.post("/select")
@login_required
async def select_sound(
    request: Request,
    sound_id: int = Form(...),
) -> RedirectResponse:
    request.app.state.db.set_active_sound(sound_id)
    request.app.state.db.set_sound_mix_layers(
        [SoundMixLayer(sound_id=sound_id, volume_percent=100)]
    )
    request.app.state.scheduler.evaluate_playback()
    sound = request.app.state.db.get_sound(sound_id)
    request.session["sound_message"] = (
        f"{sound.display_name} is now the only layer in the current mix."
        if sound
        else "Current mix updated."
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
            int(
                request.app.state.db.get_setting(
                    "volume_percent",
                    DEFAULT_VOLUME_PERCENT,
                )
            ),
        )
        request.session["sound_message"] = str(result["message"])
    else:
        request.session["sound_message"] = "That sound file is missing from disk."
    return RedirectResponse(url="/sounds", status_code=303)


@router.post("/test-mix")
@login_required
async def test_mix(request: Request) -> RedirectResponse:
    layers = request.app.state.db.resolve_sound_mix_layers()
    if not layers:
        request.session["sound_message"] = "Select at least one sound layer first."
        return RedirectResponse(url="/sounds", status_code=303)

    try:
        mix_source = request.app.state.sound_mixer.playback_source(layers)
    except RuntimeError as exc:
        request.app.state.audio.report_error(str(exc))
        request.session["sound_message"] = str(exc)
        return RedirectResponse(url="/sounds", status_code=303)

    if mix_source is None or not mix_source.exists():
        request.session["sound_message"] = "The current mix could not be prepared."
        return RedirectResponse(url="/sounds", status_code=303)

    result = request.app.state.audio.test(
        mix_source,
        int(
            request.app.state.db.get_setting(
                "volume_percent",
                DEFAULT_VOLUME_PERCENT,
            )
        ),
    )
    request.session["sound_message"] = str(result["message"])
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
    if request.app.state.db.get_state("sound_mix_layers", None) is not None:
        request.app.state.db.remove_sound_from_mix(sound_id)
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
