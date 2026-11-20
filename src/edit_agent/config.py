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
    font_bold: Path | None = None

    @property
    def music_dir(self) -> Path:
        return self.workspace / "music"

    @property
    def jobs_dir(self) -> Path:
        return self.workspace / "jobs"


def _find_bold_font() -> Path | None:
    """Font đậm có dấu tiếng Việt, theo thư mục font chuẩn của hệ điều hành. Không có thì dùng font thường."""
    override = os.environ.get("FONT_BOLD_FILE", "").strip()
    if override:
        return Path(override)
    candidates: list[Path] = []
    system_root = os.environ.get("SystemRoot")
    if system_root:
        candidates.append(Path(system_root) / "Fonts" / "arialbd.ttf")
    candidates += [
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    return next((p for p in candidates if p.exists()), None)


def _env(name: str, default: str) -> str:
    """Biến rỗng được coi như chưa đặt, dùng giá trị mặc định."""
    return os.environ.get(name, "").strip() or default


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or REPO_ROOT / ".env")
    workspace = Path(_env("EDIT_WORKSPACE", str(REPO_ROOT / "workspace")))
    font_env = _env("FONT_FILE", "")
    font = Path(font_env) if font_env else next((p for p in _font_candidates() if p.exists()), None)
    return Settings(
        workspace=workspace,
        ffmpeg=_env("FFMPEG_BIN", "ffmpeg"),
        ffprobe=_env("FFPROBE_BIN", "ffprobe"),
        edit_model=_env("EDIT_MODEL", "claude-sonnet-5-5"),
        whisper_model=_env("WHISPER_MODEL", "small"),
        tts_provider=_env("TTS_PROVIDER", "voicestudio"),
        tts_voice=_env("TTS_VOICE", ""),
        font_file=font,
        font_bold=_find_bold_font(),
    )


def require_tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"Không thấy '{name}' trong PATH. Cài ffmpeg (có ffprobe) rồi chạy lại.")
    return found
