"""Giọng đọc (TTS) qua adapter.

- voicestudio (mặc định): gọi API của Voice Studio chạy trên máy (cổng 8891, xem docs/API.md của repo TTS).
  Không nhúng mã của Voice Studio vào đây; chỉ gọi HTTP.
- openai: dự phòng, cần OPENAI_API_KEY.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import httpx


class TTSError(RuntimeError):
    pass


class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, out: Path) -> None: ...


class VoiceStudioTTS:
    """Gọi Voice Studio: /api/voices để chọn giọng, /api/synthesize (async) rồi poll job, tải audio."""

    name = "voicestudio"

    def __init__(
        self,
        base_url: str,
        voice: str,
        engine: str = "omnivoice",
        speed: float = 1.0,
        app_token: str | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        timeout_s: float = 300.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._voice = voice
        self._engine = engine
        # Tốc độ 1,0 (tự nhiên). Đo lặp 3 lần: 1,0 đạt 73%, 0,8 đạt 69%, không khác có ý nghĩa.
        self._speed = speed
        self._token = app_token
        self._client = client or httpx.Client(timeout=120)
        self._sleep = sleep
        self._timeout_s = timeout_s
        self._voice_id: str | None = None

    def _headers(self) -> dict[str, str]:
        return {"X-App-Token": self._token} if self._token else {}

    def _check(self, resp: httpx.Response, what: str) -> dict:
        if resp.status_code == 402:
            raise TTSError("Voice Studio chưa kích hoạt bản quyền (402). Mở app và kích hoạt.")
        if resp.status_code != 200:
            # Không in nội dung phản hồi để tránh lộ thông tin vào log.
            raise TTSError(f"Voice Studio lỗi ở bước {what}: HTTP {resp.status_code}")
        return resp.json()

    def resolve_voice(self) -> str:
        if self._voice_id:
            return self._voice_id
        data = self._check(self._client.get(f"{self._base}/api/voices", headers=self._headers()), "lấy danh sách giọng")
        wanted = self._voice.strip().lower()
        for v in data:
            if v.get("id") == self._voice or str(v.get("name", "")).strip().lower() == wanted:
                self._voice_id = v["id"]
                return self._voice_id
        names = ", ".join(str(v.get("name")) for v in data[:20])
        raise TTSError(f"Không thấy giọng '{self._voice}'. Các giọng hiện có: {names}")

    def synthesize(self, text: str, out: Path) -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        voice_id = self.resolve_voice()
        body = {
            "voiceId": voice_id,
            "text": text,
            "engine": self._engine,
            "speed": self._speed,
            "async": True,
        }
        started = self._check(
            self._client.post(f"{self._base}/api/synthesize", json=body, headers=self._headers()), "tạo việc"
        )
        job_id = started.get("jobId")
        if not job_id:
            raise TTSError("Voice Studio không trả jobId")

        deadline = time.monotonic() + self._timeout_s
        while True:
            job = self._check(
                self._client.get(f"{self._base}/api/synthesize/job/{job_id}", headers=self._headers()),
                "kiểm tra việc",
            )
            status = job.get("status")
            if status == "done":
                break
            if status == "error":
                raise TTSError(f"Voice Studio tạo giọng lỗi: {str(job.get('error', ''))[:200]}")
            if time.monotonic() > deadline:
                raise TTSError("Voice Studio quá thời gian chờ")
            self._sleep(1.0)

        audio_url = job.get("audioUrl") or ""
        if not audio_url:
            raise TTSError("Voice Studio không trả audioUrl")
        params = {"token": self._token} if self._token else None
        resp = self._client.get(f"{self._base}{audio_url}", params=params, timeout=120)
        if resp.status_code != 200:
            raise TTSError(f"Không tải được audio: HTTP {resp.status_code}")
        out.write_bytes(resp.content)


class OpenAITTS:
    """Dự phòng: API tạo giọng nói của OpenAI, xuất MP3."""

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
            raise TTSError(f"TTS lỗi HTTP {resp.status_code}")
        out.write_bytes(resp.content)


def make_provider(name: str, voice: str) -> TTSProvider:
    if name == "voicestudio":
        base = os.environ.get("TTS_BASE_URL", "http://127.0.0.1:8891")
        # omnivoice đọc tiếng Việt tốt hơn vieneu trên cùng 4 câu thử (2026-11-20, xem docs/QA.md).
        engine = os.environ.get("TTS_ENGINE", "omnivoice")
        token = os.environ.get("VOICE_STUDIO_TOKEN") or None
        speed = float(os.environ.get("TTS_SPEED", "").strip() or "1.0")
        return VoiceStudioTTS(base_url=base, voice=voice, engine=engine, speed=speed, app_token=token)
    if name == "openai":
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise TTSError("Thiếu OPENAI_API_KEY trong .env cho TTS.")
        return OpenAITTS(api_key=key, voice=voice)
    raise TTSError(f"Chưa hỗ trợ nhà cung cấp TTS: {name}")
