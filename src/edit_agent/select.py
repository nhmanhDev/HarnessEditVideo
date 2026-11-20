"""Chọn đoạn cắt tự động theo độ chi tiết và độ đa dạng của khung hình.

Khung trống (rèm, tường) ít cạnh; khung có sản phẩm và tay nhiều cạnh. Đo độ cạnh (Laplacian) rồi chọn
các cửa sổ có chi tiết cao, cách nhau, và khác nhau về hình (không lặp cùng một cảnh). Đây là gợi ý;
model hoặc người vẫn quyết định cuối.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

_SIG_W, _SIG_H = 16, 28


@dataclass(frozen=True)
class Window:
    start: float
    end: float
    score: float

    def to_dict(self) -> dict:
        return {k: round(v, 2) for k, v in asdict(self).items()}


def analyze_frames(
    ffmpeg: str, video: Path, duration: float, fps: float = 2.0, width: int = 160
) -> tuple[list[tuple[float, float]], np.ndarray]:
    """(điểm chi tiết theo thời điểm, chữ ký hình). Chữ ký là ảnh xám 16x28, dùng để so các cảnh với nhau."""
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
    lap = (
        4 * frames[:, 1:-1, 1:-1]
        - frames[:, :-2, 1:-1]
        - frames[:, 2:, 1:-1]
        - frames[:, 1:-1, :-2]
        - frames[:, 1:-1, 2:]
    )
    score = np.abs(lap).mean(axis=(1, 2))
    # Chữ ký: chia lưới 16x28 rồi lấy trung bình mỗi ô.
    sy, sx = height // _SIG_H, width // _SIG_W
    cropped = frames[:, : _SIG_H * sy, : _SIG_W * sx]
    sigs = cropped.reshape(n, _SIG_H, sy, _SIG_W, sx).mean(axis=(2, 4)).reshape(n, -1)
    times = [i / fps for i in range(n)]
    pairs = [(t, float(s)) for t, s in zip(times, score, strict=False) if t < duration]
    return pairs, sigs[: len(pairs)]


def detail_scores(
    ffmpeg: str, video: Path, duration: float, fps: float = 2.0, width: int = 160
) -> list[tuple[float, float]]:
    """(thời điểm, độ chi tiết) mỗi 1/fps giây."""
    return analyze_frames(ffmpeg, video, duration, fps, width)[0]


def pick_windows(
    scores: list[tuple[float, float]],
    count: int,
    length: float,
    duration: float,
    min_gap: float = 0.5,
    sigs: np.ndarray | None = None,
    min_diff: float = 6.0,
    motion_ref: float = 3.0,
) -> list[Window]:
    """Chọn tối đa `count` cửa sổ dài `length` giây, chi tiết cao, không chồng nhau, rải đều.

    Mỗi ứng viên bắt đầu ở một mốc lấy mẫu. Chọn tham lam theo điểm. Từ chối cửa sổ cách cửa sổ đã chọn dưới
    `min_gap` giây. Có `sigs` thì còn từ chối cửa sổ giống hình cửa sổ đã chọn (khác biệt dưới `min_diff`
    mức xám), để không lặp cùng một cảnh. Thiếu cửa sổ khác biệt thì bổ sung bằng cửa sổ chi tiết cao còn lại.
    """
    if not scores:
        return []
    step = scores[1][0] - scores[0][0] if len(scores) > 1 else 0.5
    k = max(1, int(round(length / step)))
    values = np.array([s for _, s in scores])
    candidates: list[tuple[Window, int]] = []
    for i in range(0, len(scores) - k + 1):
        start = scores[i][0]
        end = start + length
        if end > duration:
            break
        base = float(values[i : i + k].mean())
        if sigs is not None and k > 1:
            # Ưu tiên đoạn đứng yên (sản phẩm được giữ ổn định), phạt đoạn đang trượt vào hoặc ra khỏi khung.
            motion = float(np.abs(np.diff(sigs[i : i + k], axis=0)).mean())
            base = base / (1.0 + motion / motion_ref)
        candidates.append((Window(start, end, base), i))
    candidates.sort(key=lambda c: c[0].score, reverse=True)

    def apart(w: Window, c: Window) -> bool:
        return w.end + min_gap <= c.start or c.end + min_gap <= w.start

    chosen: list[tuple[Window, int]] = []
    for w, i in candidates:
        if len(chosen) >= count:
            break
        if not all(apart(w, c) for c, _ in chosen):
            continue
        if sigs is not None:
            mine = sigs[i : i + k].mean(axis=0)
            if any(float(np.abs(mine - sigs[j : j + k].mean(axis=0)).mean()) < min_diff for _, j in chosen):
                continue
        chosen.append((w, i))
    if sigs is not None and len(chosen) < count:
        for w, i in candidates:
            if len(chosen) >= count:
                break
            if all(apart(w, c) for c, _ in chosen) and (w, i) not in chosen:
                chosen.append((w, i))
    return sorted((w for w, _ in chosen), key=lambda w: w.start)


def presence_scores(
    scores: list[tuple[float, float]], sigs: np.ndarray, boundaries: list[float] | None = None
) -> list[tuple[float, float]]:
    """Độ lệch của mỗi khung so với phông (trung vị theo từng clip): cao = có sản phẩm hoặc tay trong khung.

    Khung rèm trống có độ lệch thấp (khoảng 4–6), khung có sản phẩm cao hơn hẳn (10–30). Độ chi tiết Laplacian không
    phân biệt được rèm với sản phẩm vì rèm có nếp gấp. Phông tính riêng cho từng clip, theo các ranh giới.
    """
    times = [t for t, _ in scores]
    edges = [0.0, *sorted(boundaries or []), float("inf")]
    out: list[tuple[float, float]] = []
    for a, b in zip(edges, edges[1:], strict=False):
        idx = [i for i, t in enumerate(times) if a <= t < b]
        if not idx:
            continue
        plate = np.median(sigs[idx], axis=0)
        out += [(times[i], float(np.abs(sigs[i] - plate).mean())) for i in idx]
    return sorted(out)
