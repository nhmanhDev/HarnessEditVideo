"""Nhận dạng giọng nói trên máy (faster-whisper). Không gửi âm thanh ra ngoài."""

from __future__ import annotations

import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str
    no_speech_prob: float

    def to_dict(self) -> dict:
        return asdict(self)


def read_wav_float32(path: Path) -> np.ndarray:
    # Đọc bằng thư viện chuẩn để tránh phụ thuộc av, gây lỗi trên một số bản cài.
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(wav: Path, model_name: str, language: str | None) -> list[TranscriptSegment]:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(
        read_wav_float32(wav),
        language=language,
        beam_size=5,
        vad_filter=False,
        condition_on_previous_text=False,
    )
    return [
        TranscriptSegment(
            start=float(s.start),
            end=float(s.end),
            text=s.text.strip(),
            no_speech_prob=float(s.no_speech_prob),
        )
        for s in segments
        if s.text.strip()
    ]
