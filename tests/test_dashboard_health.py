from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.dashboard_health import build_dashboard_health


class FakeHealthScheduler:
    def __init__(self, *, last_sync_ok: bool, last_sync_message: str) -> None:
        self.last_sync_ok = last_sync_ok
        self.last_sync_message = last_sync_message
        self.last_sync_at = "2026-07-01T18:00:00+00:00"


class FakeHealthAudio:
    def __init__(self, *, error: str | None = None, loop_backend: str | None = "mpv") -> None:
        self._error = error
        self._loop_backend = loop_backend

    def status(self) -> dict[str, str | None]:
        return {
            "state": "error" if self._error else "idle",
            "backend": self._loop_backend,
            "error": self._error,
        }

    def diagnostics(self) -> dict[str, object]:
        return {
            "loop_backend": self._loop_backend,
            "selected_output_device_label": "System default",
            "selected_output_device_description": "Use the operating system default output device.",
            "output_device_available": True,
        }


def test_dashboard_health_reports_all_systems_healthy(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        monkeypatch.setattr(
            "app.dashboard_health.load_update_status",
            lambda config: {"update_available": False, "install_requested": False, "last_error": None},
        )
        config = SimpleNamespace(
            is_production=True,
            paths=SimpleNamespace(root=Path(temp_dir)),
        )

        summary = build_dashboard_health(
            config,
            FakeHealthScheduler(last_sync_ok=True, last_sync_message="Synced 9 block(s)"),
            FakeHealthAudio(),
            timezone_name="America/New_York",
        )

        assert summary["headline"] == "All systems healthy"
        assert summary["warning_count"] == 0
        assert len(summary["checks"]) == 5


def test_dashboard_health_flags_update_and_audio_issues(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        monkeypatch.setattr(
            "app.dashboard_health.load_update_status",
            lambda config: {"update_available": False, "install_requested": False, "last_error": "Git fetch failed"},
        )
        config = SimpleNamespace(
            is_production=True,
            paths=SimpleNamespace(root=Path(temp_dir)),
        )

        summary = build_dashboard_health(
            config,
            FakeHealthScheduler(last_sync_ok=False, last_sync_message="Sync warning: auth failed"),
            FakeHealthAudio(error="No Linux audio output device is available."),
            timezone_name="America/New_York",
        )

        assert summary["warning_count"] >= 2
        assert summary["headline"].endswith("need attention")
