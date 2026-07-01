from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from app.models import ResolvedSoundMixLayer

MIX_RENDER_SECONDS = 600
PREVIEW_RENDER_SECONDS = 45
NORMALIZED_TARGET_LUFS = -18.0


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
            "preview_seconds": PREVIEW_RENDER_SECONDS,
            "normalization_supported": bool(ffmpeg_path),
            "normalization_target_lufs": NORMALIZED_TARGET_LUFS,
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

        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            first_layer = layers[0]
            if len(layers) == 1 and first_layer.volume_percent == 100:
                return first_layer.sound.path
            raise RuntimeError(
                "Install ffmpeg to use layered mixes, loudness normalization, or per-layer sound levels."
            )
        return self._render_mix(
            Path(ffmpeg_path),
            layers,
            purpose="playback",
            output_suffix=".flac",
            duration_seconds=MIX_RENDER_SECONDS,
            codec="flac",
        )

    def preview_source(self, layers: list[ResolvedSoundMixLayer]) -> Path | None:
        if not layers:
            return None

        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            first_layer = layers[0]
            if len(layers) == 1 and first_layer.volume_percent == 100:
                return first_layer.sound.path
            raise RuntimeError(
                "Install ffmpeg to preview layered mixes in the browser."
            )
        return self._render_mix(
            Path(ffmpeg_path),
            layers,
            purpose="preview",
            output_suffix=".wav",
            duration_seconds=PREVIEW_RENDER_SECONDS,
            codec="pcm_s16le",
        )

    def _render_mix(
        self,
        ffmpeg_path: Path,
        layers: list[ResolvedSoundMixLayer],
        *,
        purpose: str,
        output_suffix: str,
        duration_seconds: int,
        codec: str,
    ) -> Path:
        output_path = self.mix_dir / (
            f"{self._mix_fingerprint(layers, purpose=purpose, duration_seconds=duration_seconds)}"
            f"{output_suffix}"
        )
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
                f"[{index}:a]loudnorm=I={NORMALIZED_TARGET_LUFS:.1f}:LRA=11:TP=-1.5,"
                f"volume={max(0, min(layer.volume_percent, 100)) / 100:.4f}"
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
                str(duration_seconds),
                "-ar",
                "44100",
                "-ac",
                "2",
                "-c:a",
                codec,
                str(output_path),
            ]
        )
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as exc:
            output_path.unlink(missing_ok=True)
            raise RuntimeError("ffmpeg could not build the layered mix.") from exc
        return output_path

    def _mix_fingerprint(
        self,
        layers: list[ResolvedSoundMixLayer],
        *,
        purpose: str,
        duration_seconds: int,
    ) -> str:
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
        encoded = json.dumps(
            {
                "purpose": purpose,
                "duration_seconds": duration_seconds,
                "layers": payload,
                "normalization_target_lufs": NORMALIZED_TARGET_LUFS,
            },
            sort_keys=True,
        ).encode("utf-8")
        return f"mix-{hashlib.sha256(encoded).hexdigest()[:16]}"
