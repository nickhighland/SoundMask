from __future__ import annotations

from tempfile import TemporaryDirectory

from app.config import AppConfig, AppPaths
from app.log_viewer import available_sources, read_log_source


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


def test_available_sources_include_expected_logs():
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)

        sources = available_sources(config)

        assert [source.key for source in sources] == ["app", "service", "updates"]


def test_read_log_source_tails_recent_lines():
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        config.paths.logs.mkdir(parents=True, exist_ok=True)
        log_file = config.paths.logs / "soundmask.log"
        log_file.write_text("one\ntwo\nthree\n", encoding="utf-8")

        payload = read_log_source(config, "app", lines=2)

        assert payload["source"] == "app"
        assert payload["content"] == "two\nthree"
        assert payload["modified_at"] is not None
