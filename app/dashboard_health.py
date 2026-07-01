from __future__ import annotations

from datetime import datetime
from pathlib import Path
from shutil import disk_usage
from typing import Any

from app.display import format_datetime_label
from app.timezones import localize_datetime
from app.update_manager import load_status as load_update_status


def _bytes_label(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(max(0, value))
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    precision = 0 if unit_index == 0 else 1
    return f"{size:.{precision}f} {units[unit_index]}"


def _health_item(
    *,
    label: str,
    state: str,
    value: str,
    detail: str,
) -> dict[str, str]:
    return {
        "label": label,
        "state": state,
        "value": value,
        "detail": detail,
    }


def build_dashboard_health(
    config: Any,
    scheduler: Any,
    audio: Any,
    *,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    audio_status = audio.status()
    audio_diagnostics = audio.diagnostics()
    update_status = load_update_status(config)

    calendar_detail = scheduler.last_sync_message
    if scheduler.last_sync_at:
        last_sync_at = datetime.fromisoformat(str(scheduler.last_sync_at))
        calendar_detail = (
            f"{calendar_detail} at "
            f"{format_datetime_label(localize_datetime(last_sync_at, timezone_name))}"
        )
    calendar_item = _health_item(
        label="Calendar sync",
        state="ok" if scheduler.last_sync_ok else "warning",
        value="Healthy" if scheduler.last_sync_ok else "Needs attention",
        detail=calendar_detail,
    )

    loop_backend = str(audio_diagnostics.get("loop_backend") or "Unavailable")
    if audio_status.get("error") or loop_backend == "Unavailable":
        audio_item = _health_item(
            label="Audio backend",
            state="warning",
            value="Playback issue",
            detail=str(audio_status.get("error") or "No playback backend is available."),
        )
    elif loop_backend == "mpv":
        audio_item = _health_item(
            label="Audio backend",
            state="ok",
            value="Ready",
            detail="mpv is active for appliance playback.",
        )
    else:
        audio_item = _health_item(
            label="Audio backend",
            state="neutral",
            value=f"Using {loop_backend}",
            detail="Playback will work, but mpv gives the best loop control.",
        )

    selected_output_device_label = str(
        audio_diagnostics.get("selected_output_device_label") or "System default"
    )
    output_device_description = str(
        audio_diagnostics.get("selected_output_device_description")
        or "Using the default output device."
    )
    output_device_available = bool(audio_diagnostics.get("output_device_available", True))
    output_item = _health_item(
        label="Output device",
        state="ok" if output_device_available else "warning",
        value=selected_output_device_label,
        detail=output_device_description,
    )

    if config.is_production:
        if update_status.get("last_error"):
            updates_item = _health_item(
                label="Updates",
                state="warning",
                value="Update issue",
                detail=str(update_status["last_error"]),
            )
        elif update_status.get("install_requested"):
            updates_item = _health_item(
                label="Updates",
                state="neutral",
                value="Install queued",
                detail="SoundMask is waiting for the Linux installer to apply the update.",
            )
        elif update_status.get("update_available"):
            updates_item = _health_item(
                label="Updates",
                state="neutral",
                value="Update available",
                detail="A newer commit is ready to install from the Updates page.",
            )
        else:
            updates_item = _health_item(
                label="Updates",
                state="ok",
                value="Up to date",
                detail="Daily background checks are healthy.",
            )
    else:
        updates_item = _health_item(
            label="Updates",
            state="neutral",
            value="Development mode",
            detail="Manual update checks are available from the Updates page.",
        )

    usage = disk_usage(Path(config.paths.root))
    free_percent = (usage.free / usage.total) * 100 if usage.total else 0
    storage_item = _health_item(
        label="Disk space",
        state="warning" if usage.free < 2 * 1024**3 or free_percent < 10 else "ok",
        value=f"{free_percent:.0f}% free",
        detail=f"{_bytes_label(usage.free)} free of {_bytes_label(usage.total)}.",
    )

    items = [
        calendar_item,
        audio_item,
        output_item,
        updates_item,
        storage_item,
    ]
    warning_count = sum(1 for item in items if item["state"] == "warning")
    ok_count = sum(1 for item in items if item["state"] == "ok")
    if warning_count:
        headline = f"{warning_count} check{'s' if warning_count != 1 else ''} need attention"
    elif ok_count == len(items):
        headline = "All systems healthy"
    else:
        headline = "System ready"

    return {
        "headline": headline,
        "checks": items,
        "warning_count": warning_count,
    }
