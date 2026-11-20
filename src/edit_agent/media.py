"""Gọi ffmpeg và ffprobe: đọc thông số, tách âm thanh và khung hình."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Probe:
    duration: float
    width: int
    height: int
    has_audio: bool


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-12:])
        raise RuntimeError(f"Lệnh lỗi ({cmd[0]}):\n{tail}")
    return result


def probe(ffprobe: str, path: Path) -> Probe:
    out = run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    data = json.loads(out.stdout)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    if video is None:
        raise RuntimeError("File không có luồng hình, không phải video.")
    has_audio = any(s.get("codec_type") == "audio" for s in data["streams"])
    return Probe(
        duration=float(data["format"]["duration"]),
        width=int(video["width"]),
        height=int(video["height"]),
        has_audio=has_audio,
    )


def extract_audio_wav(ffmpeg: str, src: Path, dst: Path) -> Path:
    """WAV mono 16 kHz, đủ cho nhận dạng giọng nói."""
    run([ffmpeg, "-y", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(dst)])
    return dst


def extract_frames(
    ffmpeg: str, src: Path, out_dir: Path, duration: float, max_frames: int = 30
) -> list[tuple[float, Path]]:
    """Lấy khung hình đều nhau để model xem cấu trúc video. Trả về (thời điểm, đường dẫn)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    interval = max(duration / max_frames, 1.0)
    fps_expr = f"1/{interval:.3f}"
    run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-vf",
            f"fps={fps_expr},scale=480:-2",
            "-q:v",
            "5",
            str(out_dir / "f_%03d.jpg"),
        ]
    )
    files = sorted(out_dir.glob("f_*.jpg"))
    return [(i * interval, f) for i, f in enumerate(files)]
