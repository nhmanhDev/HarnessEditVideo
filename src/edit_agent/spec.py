"""Hợp đồng dữ liệu: yêu cầu của người dùng và kế hoạch dựng do model trả về."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class JobType(StrEnum):
    # Loại 1: chữ + nhạc, không lời.
    TEXT_MUSIC = "text_music"
    # Loại 2: có lời + nhạc nền + phụ đề (tuỳ chọn).
    SPEECH_CAPTION = "speech_music_caption"


class JobSpec(BaseModel):
    input: str = Field(description="Link Google Drive công khai hoặc đường dẫn file cục bộ")
    job_type: JobType
    # 1440x2560: kích thước các reel mẫu đạt (đo 2026-11-20).
    width: int = 1440
    height: int = 2560
    fps: int = 30
    fit: Literal["blur", "crop"] = Field(default="blur", description="Khung ngang: nền mờ (giữ hình) hoặc cắt giữa")
    captions: bool = False
    max_output_seconds: float = Field(default=60.0, gt=0)
    language: str | None = Field(default=None, description="Mã ngôn ngữ nói, ví dụ vi; để trống thì tự nhận")
    style_notes: str = ""


class Segment(BaseModel):
    src_start: float = Field(ge=0)
    src_end: float = Field(gt=0)


class TextOverlay(BaseModel):
    text: str = Field(min_length=1, max_length=120)
    start: float = Field(ge=0, description="Thời điểm trên timeline đầu ra")
    end: float = Field(gt=0)
    position: Literal["top", "center", "bottom"] = "bottom"


class VoiceLine(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    start: float = Field(ge=0, description="Thời điểm trên timeline đầu ra")
    end: float = Field(gt=0)
    caption: bool = Field(default=True, description="False: đọc nhưng không hiện phụ đề (cảnh có chữ in sẵn)")


class Music(BaseModel):
    track: str | None = Field(default=None, description="id trong workspace/music/manifest.json")
    volume: float = Field(default=0.25, ge=0, le=1)


class EditPlan(BaseModel):
    segments: list[Segment] = Field(min_length=1, description="Các đoạn cắt từ video nguồn, theo thứ tự phát")
    texts: list[TextOverlay] = Field(default_factory=list)
    voice_lines: list[VoiceLine] = Field(default_factory=list)
    music: Music = Field(default_factory=Music)
    notes: str = Field(default="", description="Lý do ngắn gọn cho các quyết định dựng")
