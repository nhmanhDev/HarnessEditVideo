"""Contact sheet có nhãn thời gian: một ảnh gồm nhiều khung hình để model xem một đoạn video trong một lần đọc."""

from __future__ import annotations

import math
from pathlib import Path

from .media import run


def make_sheet(
    ffmpeg: str,
    cwd: Path,
    src_rel: str,
    out_rel: str,
    duration: float,
    font_rel: str = "font.ttf",
    max_frames: int = 36,
    tile_w: int = 240,
    cols: int = 6,
    start: float = 0.0,
) -> str:
    """Tạo ảnh lưới khung hình từ `duration` giây của video bắt đầu ở `start`; mỗi ô ghi thời điểm (giây).

    Nhãn thời gian luôn là thời điểm trong video gốc (đã cộng `start`). ffmpeg chạy với cwd = thư mục job,
    nên mọi đường dẫn là tương đối (font.ttf nằm trong thư mục job).
    """
    interval = max(duration / max_frames, 0.5)
    frames = max(1, math.ceil(duration / interval))
    rows = max(1, math.ceil(frames / cols))
    label = (
        f"drawtext=fontfile={font_rel}:text='%{{pts\\:flt\\:{start:.2f}}}s':x=6:y=6:fontsize=22:"
        "fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=4"
    )
    vf = f"fps=1/{interval:.3f},scale={tile_w}:-2,{label},tile={cols}x{rows}:padding=3:margin=3:color=black"
    cmd = [ffmpeg, "-y", "-loglevel", "error"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-t", f"{duration:.3f}", "-i", src_rel, "-vf", vf, "-frames:v", "1", "-q:v", "3", out_rel]
    run(cmd, cwd=cwd)
    return out_rel


def make_source_sheets(
    ffmpeg: str, cwd: Path, src_rel: str, duration: float, prefix: str = "sheet_source", chunk: float = 60.0
) -> list[str]:
    """Video ngắn: một ảnh lưới. Video dài (nhiều clip gộp): chia theo từng đoạn `chunk` giây, tối đa 6 ảnh."""
    if duration <= chunk * 1.2:
        return [make_sheet(ffmpeg, cwd, src_rel, f"{prefix}.jpg", duration)]
    n = min(6, math.ceil(duration / chunk))
    length = duration / n
    return [
        make_sheet(ffmpeg, cwd, src_rel, f"{prefix}_{i + 1}.jpg", length, max_frames=30, start=i * length)
        for i in range(n)
    ]
