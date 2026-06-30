from __future__ import annotations

from tempfile import TemporaryDirectory

from app.config import AppConfig, AppPaths
from app.update_manager import (
    CHECK_REQUEST_FILE_NAME,
    INSTALL_REQUEST_FILE_NAME,
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
