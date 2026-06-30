#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/SoundMask"
DATA_ROOT="/var/lib/soundmask"
CONFIG_ROOT="/etc/soundmask"
ENV_FILE="$CONFIG_ROOT/soundmask.env"
APP_USER="soundmask"
APP_GROUP="soundmask"
SERVICE_NAME="soundmask.service"
SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=""
else
  if ! command -v sudo >/dev/null 2>&1; then
    echo "sudo is required when running install-linux.sh as a non-root user." >&2
    exit 1
  fi
  SUDO="sudo"
fi

run_as_root() {
  if [[ -n "$SUDO" ]]; then
    "$SUDO" "$@"
  else
    "$@"
  fi
}

ensure_git_safe_directory() {
  local repo_path="$1"
  local existing=""

  existing="$(run_as_root git config --system --get-all safe.directory 2>/dev/null || true)"
  if printf '%s\n' "$existing" | grep -Fxq "$repo_path"; then
    return
  fi
  run_as_root git config --system --add safe.directory "$repo_path"
}

ensure_env_default() {
  local key="$1"
  local desired="$2"
  local legacy="${3:-}"
  local current=""

  if run_as_root test -f "$ENV_FILE" && run_as_root grep -q "^${key}=" "$ENV_FILE"; then
    current="$(run_as_root awk -F= -v key="$key" '$1 == key {print substr($0, index($0, "=") + 1)}' "$ENV_FILE" | tail -n 1)"
    if [[ -n "$legacy" && "$current" == "$legacy" ]]; then
      run_as_root sed -i "s|^${key}=.*|${key}=${desired}|" "$ENV_FILE"
    fi
    return
  fi

  run_as_root sh -c "printf '%s\n' '${key}=${desired}' >> '$ENV_FILE'"
}

disable_service_if_present() {
  local service_name="$1"
  if run_as_root systemctl list-unit-files "$service_name" >/dev/null 2>&1; then
    run_as_root systemctl disable --now "$service_name" >/dev/null 2>&1 || true
  fi
}

run_as_root apt update
run_as_root apt install -y \
  python3 \
  python3-venv \
  python3-pip \
  ffmpeg \
  mpv \
  sqlite3 \
  alsa-utils \
  avahi-daemon \
  git \
  rsync

if ! id -u "$APP_USER" >/dev/null 2>&1; then
  run_as_root useradd \
    --system \
    --user-group \
    --create-home \
    --home-dir "$DATA_ROOT" \
    --shell /usr/sbin/nologin \
    "$APP_USER"
fi
if getent group audio >/dev/null 2>&1; then
  run_as_root usermod -a -G audio "$APP_USER"
fi

run_as_root install -d -m 0755 "$APP_ROOT"
if [[ "$SOURCE_ROOT" != "$APP_ROOT" ]]; then
  run_as_root rsync -a \
    --chown=root:root \
    --delete \
    --exclude ".venv/" \
    --exclude "__pycache__/" \
    --exclude ".pytest_cache/" \
    --exclude ".mypy_cache/" \
    --exclude "htmlcov/" \
    --exclude "dist/" \
    --exclude "build/" \
    --exclude "data/" \
    "$SOURCE_ROOT/" "$APP_ROOT/"
fi
if [[ -d "$APP_ROOT/.git" ]]; then
  run_as_root chown -R "$APP_USER:$APP_GROUP" "$APP_ROOT/.git"
  ensure_git_safe_directory "$APP_ROOT"
fi
cd "$APP_ROOT"

run_as_root install -d -m 0755 "$CONFIG_ROOT"
run_as_root install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$DATA_ROOT"
run_as_root install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 \
  "$DATA_ROOT/sounds" \
  "$DATA_ROOT/tokens" \
  "$DATA_ROOT/logs"
if [[ -f "$DATA_ROOT/SoundMask.sqlite" ]]; then
  run_as_root sqlite3 "$DATA_ROOT/SoundMask.sqlite" "
    UPDATE settings
    SET value = '70',
        updated_at = strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')
    WHERE key = 'volume_percent' AND value = '35';
  "
fi
run_as_root touch \
  "$DATA_ROOT/logs/service.log" \
  "$DATA_ROOT/logs/updates.log"
run_as_root chown "$APP_USER:$APP_GROUP" \
  "$DATA_ROOT/logs/service.log" \
  "$DATA_ROOT/logs/updates.log"

if [[ ! -f "$ENV_FILE" ]]; then
  session_secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  run_as_root cp "$APP_ROOT/systemd/soundmask.env.example" "$ENV_FILE"
  run_as_root sed -i "s|__SOUNDMASK_SESSION_SECRET__|$session_secret|" "$ENV_FILE"
fi
ensure_env_default "SOUNDMASK_HOST" "0.0.0.0" "127.0.0.1"
ensure_env_default "SOUNDMASK_PORT" "80" "8080"
ensure_env_default "SOUNDMASK_DATA_DIR" "$DATA_ROOT"
run_as_root chmod 0640 "$ENV_FILE"

run_as_root hostnamectl set-hostname soundmask
disable_service_if_present apache2.service
disable_service_if_present nginx.service

run_as_root python3 -m venv "$APP_ROOT/.venv"
run_as_root "$APP_ROOT/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
run_as_root "$APP_ROOT/.venv/bin/python" -m pip install --upgrade "$APP_ROOT"

run_as_root install -m 0644 \
  "$APP_ROOT/systemd/soundmask.service" \
  "/etc/systemd/system/$SERVICE_NAME"
run_as_root install -m 0644 \
  "$APP_ROOT/systemd/soundmask-update-check.service" \
  /etc/systemd/system/soundmask-update-check.service
run_as_root install -m 0644 \
  "$APP_ROOT/systemd/soundmask-update-check.timer" \
  /etc/systemd/system/soundmask-update-check.timer
run_as_root install -m 0644 \
  "$APP_ROOT/systemd/soundmask-update-check.path" \
  /etc/systemd/system/soundmask-update-check.path
run_as_root install -m 0644 \
  "$APP_ROOT/systemd/soundmask-update-install.service" \
  /etc/systemd/system/soundmask-update-install.service
run_as_root install -m 0644 \
  "$APP_ROOT/systemd/soundmask-update-install.path" \
  /etc/systemd/system/soundmask-update-install.path
run_as_root install -m 0644 \
  "$APP_ROOT/systemd/soundmask-network-apply.service" \
  /etc/systemd/system/soundmask-network-apply.service
run_as_root install -m 0644 \
  "$APP_ROOT/systemd/soundmask-network-apply.path" \
  /etc/systemd/system/soundmask-network-apply.path
run_as_root systemctl daemon-reload
run_as_root systemctl enable --now avahi-daemon
run_as_root systemctl enable "$SERVICE_NAME"
run_as_root systemctl restart "$SERVICE_NAME"
run_as_root systemctl enable --now soundmask-update-check.timer
run_as_root systemctl enable --now soundmask-update-check.path
run_as_root systemctl enable --now soundmask-update-install.path
run_as_root systemctl enable --now soundmask-network-apply.path
run_as_root systemctl start soundmask-update-check.service

echo "SoundMask installed."
echo "Open http://soundmask.local or http://DEVICE-IP"
echo "Change the web port later from Settings -> Web access port, or edit $ENV_FILE manually."
