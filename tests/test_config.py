from __future__ import annotations

from pathlib import Path

from app.config import _default_data_root


def test_default_data_root_uses_linux_state_dir(monkeypatch):
    monkeypatch.delenv("SOUNDMASK_DATA_DIR", raising=False)
    monkeypatch.setattr("app.config.platform.system", lambda: "Linux")

    assert _default_data_root() == Path("/var/lib/soundmask")


def test_default_data_root_expands_explicit_env(monkeypatch):
    monkeypatch.setenv("SOUNDMASK_DATA_DIR", "~/SoundMaskData")

    assert _default_data_root() == Path("~/SoundMaskData").expanduser()
