from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path
from threading import RLock


logger = logging.getLogger(__name__)


DEFAULT_VOLUME_PERCENT = 70
MAX_MPV_VOLUME_PERCENT = 150
MAX_STANDARD_VOLUME_PERCENT = 100


class AudioManager:
    def __init__(self, ipc_path: Path):
        self.ipc_path = ipc_path
        self._process: subprocess.Popen[str] | None = None
        self._current_sound: Path | None = None
        self._backend: str | None = None
        self._current_volume_percent = DEFAULT_VOLUME_PERCENT
        self._lock = RLock()
        self._last_error: str | None = None
        self.fade_in_seconds = 0

    def start(self, sound_path: Path, volume_percent: int) -> None:
        with self._lock:
            if self.is_playing() and self._current_sound == sound_path:
                self.set_volume(volume_percent)
                return
            self.stop()
            backend = self._preferred_loop_backend()
            if not backend:
                self._last_error = self._missing_backend_message()
                logger.warning(self._last_error)
                return
            if backend == "mpv":
                normalized_volume = self._normalized_volume_percent(
                    volume_percent,
                    backend,
                )
                self.ipc_path.parent.mkdir(parents=True, exist_ok=True)
                if self.ipc_path.exists():
                    self.ipc_path.unlink()
                command = [
                    "mpv",
                    "--no-video",
                    "--quiet",
                    *self._mpv_audio_args(),
                    "--loop-file=inf",
                    f"--input-ipc-server={self.ipc_path}",
                    f"--volume={normalized_volume}",
                    str(sound_path),
                ]
            else:
                normalized_volume = self._normalized_volume_percent(
                    volume_percent,
                    backend,
                )
                command = [
                    "ffplay",
                    "-nodisp",
                    "-loglevel",
                    "error",
                    "-loop",
                    "0",
                    "-volume",
                    str(normalized_volume),
                    str(sound_path),
                ]
            if self._launch_process(
                command,
                backend,
                sound_path,
                volume_percent=normalized_volume,
                env=self._backend_env(backend),
            ):
                if backend == "mpv" and self.fade_in_seconds > 0:
                    self._fade_in(normalized_volume)

    def stop(self, fade_out_seconds: int = 0) -> None:
        with self._lock:
            if not self._process:
                return
            if self._backend == "mpv" and fade_out_seconds > 0 and self.is_playing():
                self._fade_out(fade_out_seconds)
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=1)
            self._process = None
            self._current_sound = None
            self._backend = None
            if self.ipc_path.exists():
                self.ipc_path.unlink()

    def is_playing(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def set_volume(self, volume_percent: int) -> None:
        if not self.is_playing() or self._backend != "mpv":
            return
        normalized_volume = self._normalized_volume_percent(volume_percent, "mpv")
        if self._control_command(
            {"command": ["set_property", "volume", normalized_volume]},
            context="set volume",
        ):
            self._current_volume_percent = normalized_volume

    def test(
        self,
        sound_path: Path,
        volume_percent: int,
        seconds: int = 10,
    ) -> dict[str, str | bool]:
        backend = self._preferred_test_backend()
        if not backend:
            self._last_error = self._missing_backend_message()
            return {
                "ok": False,
                "message": self._last_error,
            }
        normalized_volume = self._normalized_volume_percent(volume_percent, backend)
        if backend == "mpv":
            command = [
                "mpv",
                "--no-video",
                "--quiet",
                *self._mpv_audio_args(),
                f"--volume={normalized_volume}",
                f"--length={seconds}",
                str(sound_path),
            ]
        elif backend == "ffplay":
            command = [
                "ffplay",
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "error",
                "-t",
                str(seconds),
                "-volume",
                str(normalized_volume),
                str(sound_path),
            ]
        else:
            command = [
                "afplay",
                "--time",
                str(seconds),
                "--volume",
                str(max(0.0, min(1.0, normalized_volume / 100))),
                str(sound_path),
            ]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                env=self._backend_env(backend),
            )
        except FileNotFoundError:
            self._last_error = self._missing_backend_message()
            return {
                "ok": False,
                "message": self._last_error,
            }
        time.sleep(0.2)
        if process.poll() is not None:
            _, stderr_output = process.communicate(timeout=1)
            self._last_error = self._launch_error_message(backend, stderr_output)
            return {
                "ok": False,
                "message": self._last_error,
            }
        self._last_error = None
        return {
            "ok": True,
            "message": f"Started {seconds}-second test playback via {backend}.",
        }

    def status(self) -> dict[str, str | bool | None]:
        state = "playing" if self.is_playing() else "idle"
        if self._last_error:
            state = "error"
        return {
            "state": state,
            "sound": str(self._current_sound) if self._current_sound else None,
            "backend": self._backend,
            "error": self._last_error,
        }

    def diagnostics(self) -> dict[str, str | bool | None]:
        mpv_path = shutil.which("mpv")
        ffplay_path = shutil.which("ffplay")
        afplay_path = shutil.which("afplay")
        return {
            "mpv_available": bool(mpv_path),
            "mpv_path": mpv_path,
            "ffplay_available": bool(ffplay_path),
            "ffplay_path": ffplay_path,
            "afplay_available": bool(afplay_path),
            "afplay_path": afplay_path,
            "loop_backend": self._preferred_loop_backend(),
            "test_backend": self._preferred_test_backend(),
            "last_error": self._last_error,
            "install_hint": self._install_hint(),
            "audio_device_hint": self._audio_device_hint(),
        }

    def _fade_out(self, fade_out_seconds: int) -> None:
        start_volume = self._current_volume_percent
        for step in range(fade_out_seconds * 4, -1, -1):
            volume = max(
                0,
                int(start_volume * (step / max(1, fade_out_seconds * 4))),
            )
            if not self._control_command(
                {"command": ["set_property", "volume", volume]},
                context="fade out",
            ):
                break
            time.sleep(0.25)

    def _fade_in(self, target_volume: int) -> None:
        steps = max(1, self.fade_in_seconds * 4)
        for step in range(steps + 1):
            volume = int(target_volume * (step / steps))
            if not self._control_command(
                {"command": ["set_property", "volume", volume]},
                context="fade in",
            ):
                break
            time.sleep(0.25)

    def _send_command(self, payload: dict[str, object]) -> None:
        deadline = time.monotonic() + 1.5
        last_error: OSError | None = None
        while time.monotonic() < deadline:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(0.5)
                    sock.connect(str(self.ipc_path))
                    sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
                    return
            except OSError as exc:
                last_error = exc
                time.sleep(0.05)
        if last_error is not None:
            raise last_error
        raise OSError("mpv IPC command failed before the socket became ready.")

    def _control_command(self, payload: dict[str, object], *, context: str) -> bool:
        try:
            self._send_command(payload)
            return True
        except OSError as exc:
            logger.warning("mpv control issue during %s: %s", context, exc)
            return False

    def _launch_process(
        self,
        command: list[str],
        backend: str,
        sound_path: Path,
        volume_percent: int,
        env: dict[str, str] | None = None,
    ) -> bool:
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
        except FileNotFoundError:
            self._last_error = self._missing_backend_message()
            self._process = None
            self._current_sound = None
            self._backend = None
            return False
        time.sleep(0.2)
        if process.poll() is not None:
            _, stderr_output = process.communicate(timeout=1)
            self._last_error = self._launch_error_message(backend, stderr_output)
            self._process = None
            self._current_sound = None
            self._backend = None
            return False
        self._process = process
        self._current_sound = sound_path
        self._backend = backend
        self._current_volume_percent = volume_percent
        self._last_error = None
        logger.info(
            "Started %s playback for %s",
            backend,
            sound_path.name,
        )
        return True

    def _preferred_loop_backend(self) -> str | None:
        if shutil.which("mpv"):
            return "mpv"
        if shutil.which("ffplay"):
            return "ffplay"
        return None

    def _preferred_test_backend(self) -> str | None:
        if shutil.which("mpv"):
            return "mpv"
        if shutil.which("ffplay"):
            return "ffplay"
        if shutil.which("afplay"):
            return "afplay"
        return None

    def _missing_backend_message(self) -> str:
        return (
            "No supported audio backend is available. Install mpv for full playback, "
            "or ffplay for a local fallback."
        )

    def _launch_error_message(self, backend: str, stderr_output: str) -> str:
        detail = stderr_output.strip()
        friendly_detail = self._friendly_launch_error(detail)
        if friendly_detail:
            logger.warning("%s launch issue: %s", backend, friendly_detail)
            return f"{backend} could not start playback: {friendly_detail}"
        if detail:
            logger.warning("%s launch issue: %s", backend, detail)
            return f"{backend} could not start playback: {detail}"
        return f"{backend} exited before playback started."

    def _install_hint(self) -> str:
        if platform.system().lower() == "darwin":
            return "brew install mpv"
        return "sudo apt install -y mpv"

    def _mpv_audio_args(self) -> list[str]:
        if platform.system().lower() == "linux":
            return [
                "--ao=alsa",
                f"--volume-max={MAX_MPV_VOLUME_PERCENT}",
            ]
        return [f"--volume-max={MAX_MPV_VOLUME_PERCENT}"]

    def _backend_env(self, backend: str) -> dict[str, str] | None:
        if platform.system().lower() != "linux" or backend != "ffplay":
            return None
        env = os.environ.copy()
        env.setdefault("SDL_AUDIODRIVER", "alsa")
        return env

    def _normalized_volume_percent(self, volume_percent: int, backend: str) -> int:
        ceiling = (
            MAX_MPV_VOLUME_PERCENT if backend == "mpv" else MAX_STANDARD_VOLUME_PERCENT
        )
        return max(0, min(int(volume_percent), ceiling))

    def _friendly_launch_error(self, detail: str) -> str | None:
        normalized = detail.lower()
        if not normalized:
            return None
        if (
            "unknown pcm default" in normalized
            or "cannot find card '0'" in normalized
            or "cannot get card index for 0" in normalized
            or "couldn't open play stream" in normalized
        ):
            return self._audio_device_hint()
        if "can't load config client.conf" in normalized:
            return (
                "The Linux audio stack is incomplete or no default playback "
                "device is configured. "
                f"{self._audio_device_hint()}"
            )
        return None

    def _audio_device_hint(self) -> str:
        if platform.system().lower() == "linux":
            return (
                "No Linux audio output device is available. In a VM, enable a "
                "virtual sound card. On Linux hardware, verify `aplay -l` and "
                "`alsamixer`."
            )
        return "No usable audio output device is available."
