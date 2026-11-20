"""Chọn đoạn cắt tự động theo độ chi tiết khung hình.

Khung trống (rèm, tường) ít cạnh; khung có sản phẩm và tay nhiều cạnh. Đo độ cạnh (Laplacian) rồi chọn
các cửa sổ có chi tiết cao, cách nhau, rải đều. Đây là gợi ý; model hoặc người vẫn quyết định cuối.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Window:
    start: float
    end: float
    score: float


def detail_scores(
    ffmpeg: str, video: Path, duration: float, fps: float = 2.0, width: int = 160
) -> list[tuple[float, float]]:
    """(thời điểm, độ chi tiết) mỗi 1/fps giây. Độ chi tiết = trung bình |Laplacian| trên ảnh xám."""
    height = int(width * 16 / 9)
    cmd = [
        ffmpeg,
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-vf",
        f"fps={fps},scale={width}:{height}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    frame_size = width * height
    n = len(raw) // frame_size
    frames = np.frombuffer(raw[: n * frame_size], dtype=np.uint8).reshape(n, height, width).astype(np.float32)
    # Laplacian 4 láng giềng, bỏ viền.
    lap = (
        4 * frames[:, 1:-1, 1:-1]
        - frames[:, :-2, 1:-1]
        - frames[:, 2:, 1:-1]
        - frames[:, 1:-1, :-2]
        - frames[:, 1:-1, 2:]
    )
    score = np.abs(lap).mean(axis=(1, 2))
    times = [i / fps for i in range(n)]
    return [(t, float(s)) for t, s in zip(times, score, strict=False) if t < duration]


def pick_windows(
    scores: list[tuple[float, float]],
    count: int,
    length: float,
    duration: float,
    min_gap: float = 0.5,
) -> list[Window]:
    """Chọn `count` cửa sổ dài `length` giây, điểm trung bình cao nhất, không chồng nhau, rải đều.

    Mỗi ứng viên là một cửa sổ bắt đầu ở một mốc lấy mẫu. Chọn tham lam theo điểm, nhưng từ chối cửa sổ
    cách cửa sổ đã chọn dưới `min_gap` giây, nên không lặp cùng một đoạn.
    """
    if not scores:
        return []
    step = scores[1][0] - scores[0][0] if len(scores) > 1 else 0.5
    k = max(1, int(round(length / step)))
    values = np.array([s for _, s in scores])
    candidates: list[Window] = []
    for i in range(0, len(scores) - k + 1):
        start = scores[i][0]
        end = start + length
        if end > duration:
            break
        candidates.append(Window(start, end, float(values[i : i + k].mean())))
    candidates.sort(key=lambda w: w.score, reverse=True)

    chosen: list[Window] = []
    for w in candidates:
        if len(chosen) >= count:
            break
        if all(w.end + min_gap <= c.start or c.end + min_gap <= w.start for c in chosen):
            chosen.append(w)
    return sorted(chosen, key=lambda w: w.start)
