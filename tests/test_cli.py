from __future__ import annotations

from app.cli import main
from app.config import AppConfig, AppPaths


def make_config() -> AppConfig:
    return AppConfig(
        env="test",
        host="127.0.0.9",
        port=9090,
        session_secret="test-secret",
        google_client_secret=None,
        paths=AppPaths(
            root="/tmp/soundmask",
            database="/tmp/soundmask/SoundMask.sqlite",
            sounds="/tmp/soundmask/sounds",
            tokens="/tmp/soundmask/tokens",
            logs="/tmp/soundmask/logs",
        ),
    )


def test_cli_serve_uses_config_defaults(monkeypatch):
    captured: dict[str, object] = {}
    monkeypatch.setattr("app.cli.get_config", make_config)
    monkeypatch.setattr(
        "app.cli.uvicorn.run",
        lambda app, host, port, reload: captured.update(
            {
                "app": app,
                "host": host,
                "port": port,
                "reload": reload,
            }
        ),
    )

    main([])

    assert captured == {
        "app": "app.main:app",
        "host": "127.0.0.9",
        "port": 9090,
        "reload": False,
    }


def test_cli_args_override_config(monkeypatch):
    captured: dict[str, object] = {}
    monkeypatch.setattr("app.cli.get_config", make_config)
    monkeypatch.setattr(
        "app.cli.uvicorn.run",
        lambda app, host, port, reload: captured.update(
            {
                "host": host,
                "port": port,
                "reload": reload,
            }
        ),
    )

    main(["serve", "--host", "0.0.0.0", "--port", "8181", "--reload"])

    assert captured == {
        "host": "0.0.0.0",
        "port": 8181,
        "reload": True,
    }
