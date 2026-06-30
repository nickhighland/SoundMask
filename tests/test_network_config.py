from __future__ import annotations

from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.config import AppConfig, AppPaths
from app.network_config import (
    apply_requested_change,
    load_status,
    request_path,
    request_port_change,
)


def make_config(temp_dir: str) -> AppConfig:
    return AppConfig(
        env="production",
        host="0.0.0.0",
        port=80,
        session_secret="test-secret",
        google_client_secret=None,
        paths=AppPaths(
            root=temp_dir,
            database=f"{temp_dir}/SoundMask.sqlite",
            sounds=f"{temp_dir}/sounds",
            tokens=f"{temp_dir}/tokens",
            logs=f"{temp_dir}/logs",
        ),
    )


def test_request_port_change_writes_pending_request():
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)

        status = request_port_change(config, 8081)

        assert request_path(config).exists() is True
        assert status["request_pending"] is True
        assert status["pending_port"] == 8081
        assert status["pending_soundmask_url"] == "http://soundmask.local:8081"


def test_apply_requested_change_updates_env_and_restarts_service(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        env_file = config.paths.root / "soundmask.env"
        env_file.write_text(
            "\n".join(
                [
                    "SOUNDMASK_ENV=production",
                    "SOUNDMASK_HOST=0.0.0.0",
                    "SOUNDMASK_PORT=80",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        request_port_change(config, 8081)
        captured: dict[str, object] = {}

        monkeypatch.setattr(
            "app.network_config.env_file_path",
            lambda _: env_file,
        )

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr("app.network_config.subprocess.run", fake_run)

        status = apply_requested_change(config)

        assert "SOUNDMASK_PORT=8081" in env_file.read_text(encoding="utf-8")
        assert request_path(config).exists() is False
        assert status["current_port"] == 8081
        assert status["request_pending"] is False
        assert captured["command"] == ["systemctl", "restart", "soundmask.service"]


def test_load_status_uses_current_port_when_no_request_exists():
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)

        status = load_status(config)

        assert status["current_port"] == 80
        assert status["request_pending"] is False
        assert status["current_soundmask_url"] == "http://soundmask.local"
