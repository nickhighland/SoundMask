from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import AppConfig, AppPaths
from app.update_manager import (
    CHECK_REQUEST_FILE_NAME,
    INSTALL_REQUEST_FILE_NAME,
    _run_git,
    _try_start_install_worker,
    check_for_updates,
    install_update,
    git_safe_directory,
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


def test_request_install_attempts_to_start_worker_in_production(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        config.env = "production"
        started: list[bool] = []

        monkeypatch.setattr(
            "app.update_manager._try_start_install_worker",
            lambda _config: started.append(True) or True,
        )

        status = request_install(config)

        assert started == [True]
        assert status["status_message"] == (
            "Update install requested. SoundMask is starting the Linux installer now."
        )


def test_try_start_install_worker_skips_direct_start_for_non_root(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        config.env = "production"
        commands: list[list[str]] = []

        monkeypatch.setattr("app.update_manager.os.geteuid", lambda: 1000)
        monkeypatch.setattr(
            "app.update_manager._run_command",
            lambda command, cwd: commands.append(command) or "",
        )

        started = _try_start_install_worker(config)

        assert started is False
        assert commands == []


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


def test_run_git_marks_repo_as_safe_directory(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        repo_path = Path(temp_dir)
        captured: dict[str, object] = {}

        monkeypatch.setattr("app.update_manager.app_root", lambda _config: repo_path)

        def fake_run_command(command: list[str], cwd: Path) -> str:
            captured["command"] = command
            captured["cwd"] = cwd
            return "ok"

        monkeypatch.setattr("app.update_manager._run_command", fake_run_command)

        result = _run_git(config, "status", "--short")

        assert result == "ok"
        assert captured["cwd"] == repo_path
        assert captured["command"] == [
            "git",
            "-c",
            f"safe.directory={git_safe_directory(config)}",
            "status",
            "--short",
        ]


def test_check_for_updates_preserves_repo_details_on_fetch_failure(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        repo_path = Path(temp_dir)
        (repo_path / ".git").mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr("app.update_manager.app_root", lambda _config: repo_path)

        responses = {
            ("rev-parse", "HEAD"): "abc123def456",
            ("rev-parse", "--abbrev-ref", "HEAD"): "main",
            ("remote", "get-url", "origin"): "https://github.com/nickhighland/SoundMask.git",
        }

        def fake_run_git(_config, *args):
            if args == ("fetch", "--quiet", "origin", "main"):
                raise RuntimeError("network unavailable")
            return responses[args]

        monkeypatch.setattr("app.update_manager._run_git", fake_run_git)

        status = check_for_updates(config)

        assert status["current_commit"] == "abc123def456"
        assert status["current_branch"] == "main"
        assert status["repo_url"] == "https://github.com/nickhighland/SoundMask.git"
        assert status["latest_commit"] is None
        assert status["last_error"] == "network unavailable"
        assert status["status_message"] == "Update check failed."


def test_install_update_ignores_untracked_files(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        repo_path = Path(temp_dir)
        command_calls: list[tuple[str, ...]] = []
        install_runs: list[list[str]] = []
        check_calls = {"count": 0}

        monkeypatch.setattr("app.update_manager.app_root", lambda _config: repo_path)

        def fake_check_for_updates(_config):
            check_calls["count"] += 1
            if check_calls["count"] == 1:
                return {"last_error": None, "update_available": True}
            return {"last_error": None, "update_available": False}

        def fake_run_git(_config, *args):
            command_calls.append(args)
            responses = {
                ("status", "--porcelain", "--untracked-files=no"): "",
                ("checkout", "main"): "",
                ("pull", "--ff-only", "origin", "main"): "",
            }
            return responses[args]

        def fake_run_command(command: list[str], cwd: Path) -> str:
            install_runs.append(command)
            return ""

        monkeypatch.setattr("app.update_manager.check_for_updates", fake_check_for_updates)
        monkeypatch.setattr("app.update_manager._run_git", fake_run_git)
        monkeypatch.setattr("app.update_manager._run_command", fake_run_command)

        status = install_update(config)

        assert status["last_error"] is None
        assert ("status", "--porcelain", "--untracked-files=no") in command_calls
        assert install_runs == [[
            "/bin/bash",
            str(repo_path / "scripts/install-linux.sh"),
        ]]


def test_install_update_reports_tracked_changes(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        config = make_config(temp_dir)
        repo_path = Path(temp_dir)
        install_runs: list[list[str]] = []

        monkeypatch.setattr("app.update_manager.app_root", lambda _config: repo_path)
        monkeypatch.setattr(
            "app.update_manager.check_for_updates",
            lambda _config: {"last_error": None, "update_available": True},
        )

        def fake_run_git(_config, *args):
            if args == ("status", "--porcelain", "--untracked-files=no"):
                return " M app/update_manager.py\nM  README.md"
            raise AssertionError(f"Unexpected git call: {args}")

        def fake_run_command(command: list[str], cwd: Path) -> str:
            install_runs.append(command)
            return ""

        monkeypatch.setattr("app.update_manager._run_git", fake_run_git)
        monkeypatch.setattr("app.update_manager._run_command", fake_run_command)

        status = install_update(config)

        assert install_runs == []
        assert "Tracked local changes are present in /opt/SoundMask." in status["last_error"]
        assert "app/update_manager.py" in status["last_error"]
        assert "README.md" in status["last_error"]
