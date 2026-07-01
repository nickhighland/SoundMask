from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response

from app.audio import DEFAULT_VOLUME_PERCENT, MAX_MPV_VOLUME_PERCENT
from app.auth import login_required
from app.bundled_sounds import bundled_sounds_dir
from app.models import ResolvedSoundMixLayer, SoundMixLayer
from app.sound_categories import (
    DEFAULT_UPLOAD_CATEGORY,
    available_sound_categories,
    group_sounds_by_category,
    normalize_sound_category_name,
)

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac"}

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


def _layers_from_form(
    form: Any,
    available_sound_ids: set[int],
) -> list[SoundMixLayer]:
    selected_sound_ids: list[int] = []
    for raw_value in form.getlist("selected_sound_ids"):
        try:
            sound_id = int(raw_value)
        except (TypeError, ValueError):
            continue
        if sound_id not in available_sound_ids or sound_id in selected_sound_ids:
            continue
        selected_sound_ids.append(sound_id)
    return [
        SoundMixLayer(
            sound_id=sound_id,
            volume_percent=_normalized_layer_volume(
                form.get(f"layer_volume_{sound_id}", 100)
            ),
        )
        for sound_id in selected_sound_ids
    ]


def _layer_signature(layers: list[SoundMixLayer]) -> list[tuple[int, int]]:
    return [
        (int(layer.sound_id), int(layer.volume_percent))
        for layer in layers
    ]


def _resolved_preset_rows(
    db,
    sound_mixer,
) -> list[dict[str, object]]:
    sounds_by_id = {sound.id: sound for sound in db.list_sounds()}
    current_signature = _layer_signature(db.get_sound_mix_layers())
    rows: list[dict[str, object]] = []
    for preset in db.list_sound_presets():
        resolved_layers: list[ResolvedSoundMixLayer] = []
        missing_layers = 0
        for layer in preset.layers:
            sound = sounds_by_id.get(layer.sound_id)
            if sound is None:
                missing_layers += 1
                continue
            resolved_layers.append(
                ResolvedSoundMixLayer(
                    sound=sound,
                    volume_percent=layer.volume_percent,
                )
            )
        rows.append(
            {
                "id": preset.id,
                "name": preset.name,
                "summary": sound_mixer.describe_layers(resolved_layers)
                if resolved_layers
                else "Missing sounds",
                "layer_count": len(preset.layers),
                "updated_at": preset.updated_at,
                "missing_layers": missing_layers,
                "is_active": current_signature == _layer_signature(preset.layers),
            }
        )
    return rows


def _resolved_upload_category(
    selected_category: str | None,
    new_category: str | None,
    available_categories: list[str],
) -> str:
    normalized_new_category = normalize_sound_category_name(new_category)
    if normalized_new_category:
        for existing_category in available_categories:
            if existing_category.casefold() == normalized_new_category.casefold():
                return existing_category
        return normalized_new_category

    normalized_selected_category = normalize_sound_category_name(selected_category)
    if normalized_selected_category:
        for existing_category in available_categories:
            if existing_category.casefold() == normalized_selected_category.casefold():
                return existing_category
        return normalized_selected_category

    return DEFAULT_UPLOAD_CATEGORY


@router.get("", response_class=HTMLResponse)
@login_required
async def sounds_page(request: Request) -> HTMLResponse:
    db = request.app.state.db
    audio = request.app.state.audio
    sounds = db.list_sounds()
    mix_layers = db.resolve_sound_mix_layers()
    mix_diagnostics = request.app.state.sound_mixer.diagnostics()
    bundled_sound_filenames = _bundled_sound_filenames()
    upload_categories = available_sound_categories(sounds, bundled_sound_filenames)
    return request.app.state.templates.TemplateResponse(
        request,
        "sounds.html",
        {
            "sounds": sounds,
            "sound_categories": group_sounds_by_category(
                sounds,
                bundled_sound_filenames,
            ),
            "upload_categories": upload_categories,
            "bundled_sound_filenames": bundled_sound_filenames,
            "mix_layers": mix_layers,
            "mix_layer_map": {
                layer.sound.id: layer.volume_percent for layer in mix_layers
            },
            "mix_summary": request.app.state.sound_mixer.describe_layers(mix_layers),
            "sound_presets": _resolved_preset_rows(
                db,
                request.app.state.sound_mixer,
            ),
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
    category_name: str = Form(DEFAULT_UPLOAD_CATEGORY),
    new_category_name: str = Form(""),
) -> RedirectResponse:
    filename = _safe_filename(sound_file.filename or "")
    extension = Path(filename).suffix.lower()
    if not filename or extension not in ALLOWED_EXTENSIONS:
        request.session["sound_message"] = "Upload a WAV, MP3, OGG, or FLAC file."
        return RedirectResponse(url="/sounds", status_code=303)

    available_categories = available_sound_categories(
        request.app.state.db.list_sounds(),
        _bundled_sound_filenames(),
    )
    resolved_category = _resolved_upload_category(
        category_name,
        new_category_name,
        available_categories,
    )

    target = request.app.state.config.paths.sounds / filename
    target.write_bytes(await sound_file.read())
    mime_type = sound_file.content_type or mimetypes.guess_type(filename)[0]
    sound = request.app.state.db.add_sound(
        filename,
        Path(filename).stem,
        str(target),
        mime_type,
        category=resolved_category,
    )
    if request.app.state.db.get_active_sound() is None:
        request.app.state.db.set_active_sound(sound.id)
    request.session["sound_message"] = f"Uploaded {filename} to {resolved_category}."
    return RedirectResponse(url="/sounds", status_code=303)


@router.post("/mix")
@login_required
async def update_mix(
    request: Request,
) -> RedirectResponse:
    db = request.app.state.db
    form = await request.form()
    available_sound_ids = {sound.id for sound in db.list_sounds()}
    layers = _layers_from_form(form, available_sound_ids)
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


@router.post("/presets")
@login_required
async def save_preset(
    request: Request,
    preset_name: str = Form(""),
) -> RedirectResponse:
    db = request.app.state.db
    form = await request.form()
    available_sound_ids = {sound.id for sound in db.list_sounds()}
    layers = _layers_from_form(form, available_sound_ids)
    try:
        preset = db.save_sound_preset(preset_name, layers)
    except ValueError as exc:
        request.session["sound_message"] = str(exc)
        return RedirectResponse(url="/sounds", status_code=303)
    request.session["sound_message"] = f"Saved preset {preset.name}."
    return RedirectResponse(url="/sounds", status_code=303)


@router.post("/presets/apply")
@login_required
async def apply_preset(
    request: Request,
    preset_id: str = Form(...),
) -> RedirectResponse:
    db = request.app.state.db
    preset = db.get_sound_preset(preset_id)
    if preset is None:
        request.session["sound_message"] = "That preset could not be found."
        return RedirectResponse(url="/sounds", status_code=303)
    db.set_sound_mix_layers(preset.layers)
    if len(preset.layers) == 1:
        db.set_active_sound(preset.layers[0].sound_id)
    request.app.state.scheduler.evaluate_playback()
    request.session["sound_message"] = f"Loaded preset {preset.name}."
    return RedirectResponse(url="/sounds", status_code=303)


@router.post("/presets/delete")
@login_required
async def delete_preset(
    request: Request,
    preset_id: str = Form(...),
) -> RedirectResponse:
    preset = request.app.state.db.get_sound_preset(preset_id)
    request.app.state.db.delete_sound_preset(preset_id)
    request.session["sound_message"] = (
        f"Deleted preset {preset.name}."
        if preset is not None
        else "Preset removed."
    )
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
        playback_source = sound.path
        try:
            normalized_source = request.app.state.sound_mixer.playback_source(
                [
                    ResolvedSoundMixLayer(
                        sound=sound,
                        volume_percent=100,
                    )
                ]
            )
            if normalized_source is not None:
                playback_source = normalized_source
            request.app.state.audio.clear_error()
        except RuntimeError as exc:
            request.app.state.audio.report_error(str(exc))
        result = request.app.state.audio.test(
            playback_source,
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


@router.post("/preview-builder")
@login_required
async def preview_builder_mix(
    request: Request,
) -> Response:
    db = request.app.state.db
    form = await request.form()
    available_sounds = {sound.id: sound for sound in db.list_sounds()}
    layers = _layers_from_form(form, set(available_sounds))
    if not layers:
        return PlainTextResponse(
            "Select at least one sound layer first.",
            status_code=400,
        )
    resolved_layers: list[ResolvedSoundMixLayer] = []
    for layer in layers:
        sound = available_sounds.get(layer.sound_id)
        if sound is None:
            continue
        resolved_layers.append(
            ResolvedSoundMixLayer(
                sound=sound,
                volume_percent=layer.volume_percent,
            )
        )
    if not resolved_layers:
        return PlainTextResponse(
            "The selected sounds are no longer available.",
            status_code=400,
        )
    try:
        preview_source = request.app.state.sound_mixer.preview_source(resolved_layers)
    except RuntimeError as exc:
        return PlainTextResponse(str(exc), status_code=400)
    if preview_source is None or not preview_source.exists():
        return PlainTextResponse(
            "The current preview mix could not be prepared.",
            status_code=500,
        )
    media_type = mimetypes.guess_type(preview_source.name)[0] or "application/octet-stream"
    return FileResponse(
        preview_source,
        media_type=media_type,
        filename=preview_source.name,
    )


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
