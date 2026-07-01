from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from app.models import ResolvedSoundMixLayer

MIX_RENDER_SECONDS = 600


class SoundMixManager:
    def __init__(self, mix_dir: Path):
        self.mix_dir = mix_dir
        self.mix_dir.mkdir(parents=True, exist_ok=True)

    def diagnostics(self) -> dict[str, object]:
        ffmpeg_path = shutil.which("ffmpeg")
        return {
            "ffmpeg_available": bool(ffmpeg_path),
            "ffmpeg_path": ffmpeg_path,
            "render_seconds": MIX_RENDER_SECONDS,
        }

    def describe_layers(self, layers: list[ResolvedSoundMixLayer]) -> str:
        if not layers:
            return "No mix selected"
        names = [layer.sound.display_name for layer in layers]
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} + {names[1]}"
        return f"{names[0]} + {len(names) - 1} more"

    def playback_source(self, layers: list[ResolvedSoundMixLayer]) -> Path | None:
        if not layers:
            return None
        first_layer = layers[0]
        if len(layers) == 1 and first_layer.volume_percent == 100:
            return first_layer.sound.path

        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise RuntimeError(
                "Install ffmpeg to use layered mixes or per-layer sound levels."
            )
        return self._render_mix(Path(ffmpeg_path), layers)

    def _render_mix(
        self,
        ffmpeg_path: Path,
        layers: list[ResolvedSoundMixLayer],
    ) -> Path:
        output_path = self.mix_dir / f"{self._mix_fingerprint(layers)}.flac"
        if output_path.exists():
            return output_path

        command: list[str] = [
            str(ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
        ]
        for layer in layers:
            command.extend(["-stream_loop", "-1", "-i", str(layer.sound.path)])

        filter_parts = [
            (
                f"[{index}:a]volume="
                f"{max(0, min(layer.volume_percent, 100)) / 100:.4f}"
                f"[a{index}]"
            )
            for index, layer in enumerate(layers)
        ]
        mixed_inputs = "".join(f"[a{index}]" for index in range(len(layers)))
        filter_parts.append(
            (
                f"{mixed_inputs}amix=inputs={len(layers)}:"
                "normalize=0:duration=longest,"
                "alimiter=limit=0.92[out]"
            )
        )
        command.extend(
            [
                "-filter_complex",
                ";".join(filter_parts),
                "-map",
                "[out]",
                "-t",
                str(MIX_RENDER_SECONDS),
                "-ar",
                "44100",
                "-ac",
                "2",
                "-c:a",
                "flac",
                str(output_path),
            ]
        )
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as exc:
            output_path.unlink(missing_ok=True)
            raise RuntimeError("ffmpeg could not build the layered mix.") from exc
        return output_path

    def _mix_fingerprint(self, layers: list[ResolvedSoundMixLayer]) -> str:
        payload = [
            {
                "sound_id": layer.sound.id,
                "path": str(layer.sound.path),
                "volume_percent": layer.volume_percent,
                "size": layer.sound.path.stat().st_size if layer.sound.path.exists() else 0,
                "mtime_ns": (
                    layer.sound.path.stat().st_mtime_ns
                    if layer.sound.path.exists()
                    else 0
                ),
            }
            for layer in layers
        ]
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return f"mix-{hashlib.sha256(encoded).hexdigest()[:16]}"
