from __future__ import annotations

import argparse
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.config import AppConfig, get_config


REQUEST_FILE_NAME = "network-config-request.json"
STATUS_FILE_NAME = "network-config-status.json"
ENV_FILE_PATH = Path("/etc/soundmask/soundmask.env")
SERVICE_NAME = "soundmask.service"

logger = logging.getLogger(__name__)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def request_path(config: AppConfig) -> Path:
    return config.paths.root / REQUEST_FILE_NAME


def status_path(config: AppConfig) -> Path:
    return config.paths.root / STATUS_FILE_NAME


def env_file_path(config: AppConfig) -> Path:
    if config.is_production:
        return ENV_FILE_PATH
    return Path.cwd() / ".env"


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


def _port_suffix(port: int) -> str:
    return "" if port == 80 else f":{port}"


def _access_url(host: str, port: int) -> str:
    return f"http://{host}{_port_suffix(port)}"


def _coerce_port(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _validate_port(port: int) -> int:
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535.")
    return port


def load_status(config: AppConfig) -> dict[str, Any]:
    payload = _load_json(status_path(config))
    request = _load_json(request_path(config))
    current_port = _coerce_port(payload.get("current_port"), config.port)
    pending_port = request.get("port")
    pending_port = (
        _coerce_port(pending_port, current_port)
        if pending_port is not None
        else None
    )
    payload.setdefault("current_host", config.host)
    payload["current_port"] = current_port
    payload.setdefault("last_requested_port", current_port)
    payload.setdefault("last_requested_at", None)
    payload.setdefault("last_applied_at", None)
    payload.setdefault("last_error", None)
    payload.setdefault(
        "status_message",
        f"SoundMask is currently listening on port {current_port}.",
    )
    payload["request_pending"] = request_path(config).exists()
    payload["pending_port"] = pending_port
    payload["change_requested_at"] = request.get("requested_at")
    payload["current_soundmask_url"] = _access_url("soundmask.local", current_port)
    payload["current_device_url"] = _access_url("DEVICE-IP", current_port)
    payload["pending_soundmask_url"] = (
        _access_url("soundmask.local", pending_port)
        if pending_port is not None
        else None
    )
    payload["pending_device_url"] = (
        _access_url("DEVICE-IP", pending_port)
        if pending_port is not None
        else None
    )
    return payload


def save_status(config: AppConfig, payload: dict[str, Any]) -> None:
    current = load_status(config)
    current.update(payload)
    _write_json(status_path(config), current)


def request_port_change(config: AppConfig, port: int) -> dict[str, Any]:
    port = _validate_port(port)
    current = load_status(config)
    if port == current["current_port"] and not current["request_pending"]:
        save_status(
            config,
            {
                "current_host": config.host,
                "current_port": current["current_port"],
                "last_requested_port": port,
                "last_requested_at": utcnow_iso(),
                "last_error": None,
                "status_message": f"SoundMask is already using port {port}.",
            },
        )
        return load_status(config)

    payload = {"port": port, "requested_at": utcnow_iso()}
    _write_json(request_path(config), payload)
    logger.info("Network port change requested: port=%s", port)
    save_status(
        config,
        {
            "current_host": config.host,
            "current_port": current["current_port"],
            "last_requested_port": port,
            "last_requested_at": payload["requested_at"],
            "last_error": None,
            "status_message": (
                f"Port change requested. SoundMask will restart on port {port}."
            ),
        },
    )
    return load_status(config)


def clear_request(config: AppConfig) -> None:
    request_path(config).unlink(missing_ok=True)


def _default_env_lines(config: AppConfig) -> list[str]:
    return [
        f"SOUNDMASK_ENV={config.env}",
        f"SOUNDMASK_HOST={config.host}",
        f"SOUNDMASK_PORT={config.port}",
        f"SOUNDMASK_DATA_DIR={config.paths.root}",
        f"SOUNDMASK_SESSION_SECRET={config.session_secret}",
        f"SOUNDMASK_GOOGLE_CLIENT_SECRET={config.google_client_secret or ''}",
    ]


def _write_env_updates(config: AppConfig, updates: dict[str, str]) -> None:
    path = env_file_path(config)
    lines = (
        path.read_text(encoding="utf-8").splitlines()
        if path.exists()
        else _default_env_lines(config)
    )
    pending_keys = set(updates)
    rendered: list[str] = []
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            rendered.append(line)
            continue
        key, _, _ = line.partition("=")
        if key in updates:
            rendered.append(f"{key}={updates[key]}")
            pending_keys.discard(key)
            continue
        rendered.append(line)
    for key in updates:
        if key in pending_keys:
            rendered.append(f"{key}={updates[key]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(rendered).rstrip() + "\n"
    with NamedTemporaryFile(
        "w",
        dir=path.parent,
        encoding="utf-8",
        delete=False,
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def apply_requested_change(config: AppConfig) -> dict[str, Any]:
    request = _load_json(request_path(config))
    if not request:
        save_status(
            config,
            {
                "last_error": None,
                "status_message": "No network change was pending.",
            },
        )
        return load_status(config)

    port = _validate_port(_coerce_port(request.get("port"), config.port))
    requested_at = request.get("requested_at")
    clear_request(config)
    try:
        _write_env_updates(config, {"SOUNDMASK_PORT": str(port)})
        subprocess.run(
            ["systemctl", "restart", SERVICE_NAME],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Network settings applied: port=%s", port)
        save_status(
            config,
            {
                "current_host": config.host,
                "current_port": port,
                "last_requested_port": port,
                "last_requested_at": requested_at,
                "last_applied_at": utcnow_iso(),
                "last_error": None,
                "status_message": (
                    f"Network settings applied. SoundMask restarted on port {port}."
                ),
            },
        )
    except Exception as exc:
        logger.warning("Network settings apply failed: %s", exc, exc_info=True)
        save_status(
            config,
            {
                "current_host": config.host,
                "current_port": config.port,
                "last_requested_port": port,
                "last_requested_at": requested_at,
                "last_error": str(exc),
                "status_message": (
                    f"Port {port} was saved, but the SoundMask service could not restart."
                ),
            },
        )
    return load_status(config)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.network_config",
        description="SoundMask network settings worker.",
    )
    parser.add_argument("command", choices=["apply"])
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = get_config()
    if args.command == "apply":
        result = apply_requested_change(config)
        if result.get("last_error"):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
