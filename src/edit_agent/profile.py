"""Hồ sơ phong cách từ video mẫu: nhịp cắt, độ dài cảnh, tỉ lệ có lời. Chỉ đo, không sao chép nội dung."""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

from .config import Settings, require_tool
from .media import extract_audio_wav, probe, run
from .transcribe import transcribe

_PTS = re.compile(r"pts_time:([0-9.]+)")


def scene_cuts(ffmpeg: str, video: Path, threshold: float = 0.3) -> list[float]:
    """Thời điểm các lần đổi cảnh, theo bộ phát hiện thay đổi khung của ffmpeg."""
    result = run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-filter:v",
            f"select='gt(scene,{threshold})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    return [float(m.group(1)) for m in _PTS.finditer(result.stderr)]


def shot_lengths(cuts: list[float], duration: float) -> list[float]:
    marks = [0.0, *[c for c in cuts if 0 < c < duration], duration]
    return [round(b - a, 3) for a, b in zip(marks, marks[1:], strict=False) if b - a > 0.05]


def profile_videos(videos: list[Path], out: Path, settings: Settings, with_speech: bool = True) -> dict:
    ffmpeg = require_tool(settings.ffmpeg)
    ffprobe = require_tool(settings.ffprobe)
    items = []
    work = out.parent / f"{out.stem}-work"
    work.mkdir(parents=True, exist_ok=True)
    for v in videos:
        info = probe(ffprobe, v)
        cuts = scene_cuts(ffmpeg, v)
        lengths = shot_lengths(cuts, info.duration)
        speech_ratio = None
        speech_seconds = None
        if with_speech and info.has_audio:
            wav = extract_audio_wav(ffmpeg, v, work / f"{v.stem}.wav")
            segs = transcribe(wav, settings.whisper_model, None)
            spoken = sum(s.end - s.start for s in segs if s.no_speech_prob < 0.5)
            speech_seconds = round(spoken, 2)
            speech_ratio = round(spoken / info.duration, 3) if info.duration else 0.0
        items.append(
            {
                "file": v.name,
                "duration": round(info.duration, 2),
                "size": f"{info.width}x{info.height}",
                "cuts": len(cuts),
                "cuts_per_10s": round(len(cuts) / info.duration * 10, 2) if info.duration else 0,
                "shot_median_s": round(statistics.median(lengths), 2) if lengths else None,
                "shot_max_s": max(lengths) if lengths else None,
                "speech_seconds": speech_seconds,
                "speech_ratio": speech_ratio,
            }
        )
    summary = {
        "videos": len(items),
        "cuts_per_10s_median": round(statistics.median(i["cuts_per_10s"] for i in items), 2) if items else None,
        "shot_median_s": round(statistics.median(i["shot_median_s"] for i in items if i["shot_median_s"]), 2)
        if any(i["shot_median_s"] for i in items)
        else None,
        "speech_ratio_median": round(
            statistics.median(i["speech_ratio"] for i in items if i["speech_ratio"] is not None), 3
        )
        if any(i["speech_ratio"] is not None for i in items)
        else None,
    }
    data = {"summary": summary, "items": items}
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
