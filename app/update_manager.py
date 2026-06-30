from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app import __version__
from app.config import AppConfig, get_config


STATUS_FILE_NAME = "update-status.json"
CHECK_REQUEST_FILE_NAME = "update-check-request.json"
INSTALL_REQUEST_FILE_NAME = "update-install-request.json"
DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"
DEFAULT_REPO_URL = "https://github.com/nickhighland/SoundMask"
INSTALL_SERVICE_NAME = "soundmask-update-install.service"

logger = logging.getLogger(__name__)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def app_root(config: AppConfig) -> Path:
    cwd = Path.cwd()
    if (cwd / ".git").exists():
        return cwd
    return Path("/opt/SoundMask") if config.is_production else cwd


def git_safe_directory(config: AppConfig) -> str:
    return str(app_root(config).resolve())


def status_path(config: AppConfig) -> Path:
    return config.paths.root / STATUS_FILE_NAME


def check_request_path(config: AppConfig) -> Path:
    return config.paths.root / CHECK_REQUEST_FILE_NAME


def install_request_path(config: AppConfig) -> Path:
    return config.paths.root / INSTALL_REQUEST_FILE_NAME


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        dir=path.parent,
        encoding="utf-8",
        delete=False,
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def load_status(config: AppConfig) -> dict[str, Any]:
    payload = _load_json(status_path(config))
    check_request = _load_json(check_request_path(config))
    install_request = _load_json(install_request_path(config))
    payload.setdefault("repo_url", DEFAULT_REPO_URL)
    payload.setdefault("current_branch", None)
    payload.setdefault("current_version", __version__)
    payload.setdefault("current_commit", None)
    payload.setdefault("latest_commit", None)
    payload.setdefault("last_checked_at", None)
    payload.setdefault("last_install_at", None)
    payload.setdefault("last_error", None)
    payload.setdefault("status_message", "Update status has not been checked yet.")
    payload["check_requested_at"] = check_request.get("requested_at")
    payload["install_requested"] = install_request_path(config).exists()
    payload["install_requested_at"] = install_request.get("requested_at")
    payload["update_available"] = bool(payload.get("update_available", False))
    payload["install_supported"] = (app_root(config) / ".git").exists()
    return payload


def save_status(config: AppConfig, payload: dict[str, Any]) -> None:
    current = load_status(config)
    current.update(payload)
    current["current_version"] = __version__
    current["repo_url"] = current.get("repo_url") or DEFAULT_REPO_URL
    current["install_requested"] = install_request_path(config).exists()
    _write_json(status_path(config), current)


def request_check(config: AppConfig) -> dict[str, Any]:
    payload = {"requested_at": utcnow_iso()}
    _write_json(check_request_path(config), payload)
    logger.info("Update check requested.")
    save_status(
        config,
        {
            "check_requested_at": payload["requested_at"],
            "last_error": None,
            "status_message": "Update check requested.",
        },
    )
    return load_status(config)


def request_install(config: AppConfig) -> dict[str, Any]:
    clear_install_request(config)
    payload = {"requested_at": utcnow_iso()}
    _write_json(install_request_path(config), payload)
    logger.info("Update install requested.")
    started = _try_start_install_worker(config)
    save_status(
        config,
        {
            "install_requested_at": payload["requested_at"],
            "last_error": None,
            "status_message": (
                "Update install requested. SoundMask is starting the Linux installer now."
                if started
                else "Update install requested. Waiting for the Linux update worker."
            ),
        },
    )
    return load_status(config)


def clear_check_request(config: AppConfig) -> None:
    check_request_path(config).unlink(missing_ok=True)


def clear_install_request(config: AppConfig) -> None:
    install_request_path(config).unlink(missing_ok=True)


def _run_command(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(detail or "Command failed.")
    return completed.stdout.strip()


def _run_git(config: AppConfig, *args: str) -> str:
    return _run_command(
        [
            "git",
            "-c",
            f"safe.directory={git_safe_directory(config)}",
            *args,
        ],
        cwd=app_root(config),
    )


def _try_start_install_worker(config: AppConfig) -> bool:
    if not config.is_production:
        return False
    if os.geteuid() == 0:
        try:
            _run_command(["systemctl", "start", INSTALL_SERVICE_NAME], cwd=app_root(config))
            logger.info("Update install worker started: %s", INSTALL_SERVICE_NAME)
            return True
        except Exception as exc:
            logger.info(
                "Update install worker could not be started directly by root, leaving request queued: %s",
                exc,
            )
            return False
    logger.info(
        "Update install request queued for %s. The web app runs as a restricted service user, so the filesystem watcher will launch the root installer.",
        INSTALL_SERVICE_NAME,
    )
    return False


def _tracked_local_changes(config: AppConfig) -> str:
    return _run_git(
        config,
        "status",
        "--porcelain",
        "--untracked-files=no",
    )


def check_for_updates(config: AppConfig) -> dict[str, Any]:
    clear_check_request(config)
    repo_path = app_root(config)
    existing = load_status(config)
    base_payload = {
        "current_version": __version__,
        "last_checked_at": utcnow_iso(),
        "install_requested": install_request_path(config).exists(),
        "install_requested_at": _load_json(install_request_path(config)).get("requested_at"),
        "check_requested_at": None,
    }
    if not (repo_path / ".git").exists():
        logger.warning("Update check skipped because install is not a git checkout.")
        save_status(
            config,
            {
                **base_payload,
                "update_available": False,
                "status_message": "Updates are unavailable because this install is not a git checkout.",
                "last_error": None,
                "current_commit": None,
                "latest_commit": None,
                "install_supported": False,
            },
        )
        return load_status(config)

    repo_url = str(existing.get("repo_url") or DEFAULT_REPO_URL)
    current_branch = existing.get("current_branch")
    current_commit = existing.get("current_commit")
    latest_commit = existing.get("latest_commit")
    try:
        current_commit = _run_git(config, "rev-parse", "HEAD")
        current_branch = _run_git(config, "rev-parse", "--abbrev-ref", "HEAD")
        repo_url = _run_git(config, "remote", "get-url", DEFAULT_REMOTE) or DEFAULT_REPO_URL
        _run_git(config, "fetch", "--quiet", DEFAULT_REMOTE, DEFAULT_BRANCH)
        latest_commit = _run_git(config, "rev-parse", "FETCH_HEAD")
        update_available = current_commit != latest_commit
        payload = {
            **base_payload,
            "repo_url": repo_url,
            "current_branch": current_branch,
            "current_commit": current_commit,
            "latest_commit": latest_commit,
            "update_available": update_available,
            "install_supported": True,
            "last_error": None,
            "status_message": (
                "An update is ready to install."
                if update_available
                else "SoundMask is already up to date."
            ),
        }
        logger.info(
            "Update check completed: branch=%s update_available=%s",
            current_branch,
            update_available,
        )
    except Exception as exc:
        logger.warning("Update check failed: %s", exc, exc_info=True)
        payload = {
            **base_payload,
            "repo_url": repo_url,
            "current_branch": current_branch,
            "current_commit": current_commit,
            "latest_commit": latest_commit,
            "update_available": False,
            "install_supported": True,
            "last_error": str(exc),
            "status_message": "Update check failed.",
        }
    save_status(config, payload)
    return load_status(config)


def install_update(config: AppConfig) -> dict[str, Any]:
    clear_install_request(config)
    status = check_for_updates(config)
    if status.get("last_error"):
        return status
    if not status.get("update_available"):
        logger.info("Update install skipped because no update was available.")
        save_status(
            config,
            {
                "install_requested_at": None,
                "status_message": "No update was waiting to be installed.",
            },
        )
        return load_status(config)
    try:
        dirty = _tracked_local_changes(config)
        if dirty:
            raise RuntimeError(
                "Tracked local changes are present in /opt/SoundMask. "
                "Update aborted until they are committed, stashed, or discarded.\n"
                + "\n".join(f"  {line}" for line in dirty.splitlines() if line.strip())
            )
        _run_git(config, "checkout", DEFAULT_BRANCH)
        _run_git(config, "pull", "--ff-only", DEFAULT_REMOTE, DEFAULT_BRANCH)
        _run_command(
            ["/bin/bash", str(app_root(config) / "scripts/install-linux.sh")],
            cwd=app_root(config),
        )
        check_for_updates(config)
        logger.info("Update installed successfully.")
        save_status(
            config,
            {
                "last_install_at": utcnow_iso(),
                "install_requested_at": None,
                "status_message": "Update installed successfully.",
                "last_error": None,
            },
        )
        return load_status(config)
    except Exception as exc:
        logger.warning("Update install failed: %s", exc, exc_info=True)
        save_status(
            config,
            {
                "install_requested_at": None,
                "last_error": str(exc),
                "status_message": "Update install failed.",
            },
        )
        return load_status(config)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.update_manager",
        description="SoundMask update worker.",
    )
    parser.add_argument("command", choices=["check", "install"])
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = get_config()
    if args.command == "check":
        check_for_updates(config)
        return
    result = install_update(config)
    if result.get("last_error"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
