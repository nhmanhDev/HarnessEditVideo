"""Giọng đọc (TTS) qua adapter. Bản đầu dùng OpenAI; có thể thêm nhà cung cấp khác mà không đổi pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

import httpx


class TTSError(RuntimeError):
    pass


class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, out: Path) -> None: ...


class OpenAITTS:
    """Gọi API tạo giọng nói của OpenAI, xuất MP3. Cần OPENAI_API_KEY trong .env."""

    name = "openai"
    endpoint = "https://api.openai.com/v1/audio/speech"

    def __init__(self, api_key: str, voice: str, model: str = "gpt-4o-mini-tts") -> None:
        self._key = api_key
        self._voice = voice
        self._model = model

    def synthesize(self, text: str, out: Path) -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        resp = httpx.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self._key}"},
            json={"model": self._model, "voice": self._voice, "input": text, "response_format": "mp3"},
            timeout=120,
        )
        if resp.status_code != 200:
            # Không in toàn bộ nội dung phản hồi để tránh lộ thông tin tài khoản vào log.
            raise TTSError(f"TTS lỗi HTTP {resp.status_code}")
        out.write_bytes(resp.content)


def make_provider(name: str, voice: str) -> TTSProvider:
    if name == "openai":
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise TTSError("Thiếu OPENAI_API_KEY trong .env cho TTS.")
        return OpenAITTS(api_key=key, voice=voice)
    raise TTSError(f"Chưa hỗ trợ nhà cung cấp TTS: {name}")
