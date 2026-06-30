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

sudo apt update
sudo apt install -y \
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
  sudo useradd \
    --system \
    --user-group \
    --create-home \
    --home-dir "$DATA_ROOT" \
    --shell /usr/sbin/nologin \
    "$APP_USER"
fi

sudo install -d -m 0755 "$APP_ROOT"
if [[ "$SOURCE_ROOT" != "$APP_ROOT" ]]; then
  sudo rsync -a \
    --delete \
    --exclude ".git/" \
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
cd "$APP_ROOT"

sudo install -d -m 0755 "$CONFIG_ROOT"
sudo install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$DATA_ROOT"
sudo install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 \
  "$DATA_ROOT/sounds" \
  "$DATA_ROOT/tokens" \
  "$DATA_ROOT/logs"

if [[ ! -f "$ENV_FILE" ]]; then
  session_secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  sudo cp "$APP_ROOT/systemd/soundmask.env.example" "$ENV_FILE"
  sudo sed -i "s|__SOUNDMASK_SESSION_SECRET__|$session_secret|" "$ENV_FILE"
fi

sudo python3 -m venv "$APP_ROOT/.venv"
sudo "$APP_ROOT/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
sudo "$APP_ROOT/.venv/bin/python" -m pip install --upgrade "$APP_ROOT"

sudo install -m 0644 \
  "$APP_ROOT/systemd/soundmask.service" \
  "/etc/systemd/system/$SERVICE_NAME"
sudo systemctl daemon-reload
sudo systemctl enable --now avahi-daemon
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

device_hostname="$(hostname)"
echo "SoundMask installed."
echo "Open http://${device_hostname}.local:8080 or http://DEVICE-IP:8080"
echo "Edit $ENV_FILE to change host, port, data path, or Google client secret path."
