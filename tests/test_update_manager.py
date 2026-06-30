from __future__ import annotations

from tempfile import TemporaryDirectory

from app.config import AppConfig, AppPaths
from app.update_manager import (
    CHECK_REQUEST_FILE_NAME,
    INSTALL_REQUEST_FILE_NAME,
    check_for_updates,
    load_status,
    request_check,
    request_install,
)


def make_config(temp_dir: str) -> AppConfig:
    return AppConfig(
        env="test",
        host="127.0.0.1",
        port=8080,
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


def test_request_check_creates_marker_file():
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)

        request_check(config)

        status = load_status(config)
        assert (config.paths.root / CHECK_REQUEST_FILE_NAME).exists()
        assert status["check_requested_at"] is not None


def test_request_install_creates_marker_file():
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)

        request_install(config)

        status = load_status(config)
        assert (config.paths.root / INSTALL_REQUEST_FILE_NAME).exists()
        assert status["install_requested"] is True


def test_check_for_updates_clears_request_and_reports_up_to_date(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        (config.paths.root / ".git").mkdir(parents=True, exist_ok=True)
        request_check(config)

        responses = {
            ("rev-parse", "HEAD"): "abc123",
            ("rev-parse", "--abbrev-ref", "HEAD"): "main",
            ("remote", "get-url", "origin"): "https://github.com/nickhighland/SoundMask.git",
            ("fetch", "--quiet", "origin", "main"): "",
            ("rev-parse", "FETCH_HEAD"): "abc123",
        }

        monkeypatch.setattr(
            "app.update_manager._run_git",
            lambda _config, *args: responses[args],
        )

        status = check_for_updates(config)

        assert (config.paths.root / CHECK_REQUEST_FILE_NAME).exists() is False
        assert status["check_requested_at"] is None
        assert status["status_message"] == "SoundMask is already up to date."
        assert status["update_available"] is False
