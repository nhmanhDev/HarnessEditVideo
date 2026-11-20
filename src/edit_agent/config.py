"""Cấu hình chạy: biến môi trường, thư mục làm việc, font và ffmpeg. Không ghi đường dẫn tuyệt đối vào mã."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]


# Font có dấu tiếng Việt, tìm theo thư mục chuẩn của từng hệ điều hành.
def _font_candidates() -> list[Path]:
    # Windows: thư mục hệ thống lấy từ biến môi trường SystemRoot, không ghi cứng ổ đĩa.
    candidates: list[Path] = []
    system_root = os.environ.get("SystemRoot")
    if system_root:
        candidates.append(Path(system_root) / "Fonts" / "arial.ttf")
    candidates += [
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    return candidates


@dataclass(frozen=True)
class Settings:
    workspace: Path
    ffmpeg: str
    ffprobe: str
    edit_model: str
    whisper_model: str
    tts_provider: str
    tts_voice: str
    font_file: Path | None

    @property
    def music_dir(self) -> Path:
        return self.workspace / "music"

    @property
    def jobs_dir(self) -> Path:
        return self.workspace / "jobs"


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or REPO_ROOT / ".env")
    workspace = Path(os.environ.get("EDIT_WORKSPACE", REPO_ROOT / "workspace"))
    font_env = os.environ.get("FONT_FILE")
    font = Path(font_env) if font_env else next((p for p in _font_candidates() if p.exists()), None)
    return Settings(
        workspace=workspace,
        ffmpeg=os.environ.get("FFMPEG_BIN", "ffmpeg"),
        ffprobe=os.environ.get("FFPROBE_BIN", "ffprobe"),
        edit_model=os.environ.get("EDIT_MODEL", "claude-sonnet-5-5"),
        whisper_model=os.environ.get("WHISPER_MODEL", "small"),
        tts_provider=os.environ.get("TTS_PROVIDER", "openai"),
        tts_voice=os.environ.get("TTS_VOICE", "alloy"),
        font_file=font,
    )


def require_tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"Không thấy '{name}' trong PATH. Cài ffmpeg (có ffprobe) rồi chạy lại.")
    return found
