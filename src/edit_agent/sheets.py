"""Contact sheet có nhãn thời gian: một ảnh gồm nhiều khung hình để model xem cả video trong một lần đọc."""

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
) -> str:
    """Tạo ảnh lưới khung hình từ video, mỗi ô ghi thời điểm (giây) ở góc. Trả về out_rel.

    ffmpeg chạy với cwd = thư mục job, nên mọi đường dẫn là tương đối (font.ttf nằm trong thư mục job).
    """
    interval = max(duration / max_frames, 0.5)
    frames = max(1, math.ceil(duration / interval))
    rows = max(1, math.ceil(frames / cols))
    label = (
        f"drawtext=fontfile={font_rel}:text='%{{pts\\:flt}}s':x=6:y=6:fontsize=22:"
        "fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=4"
    )
    vf = f"fps=1/{interval:.3f},scale={tile_w}:-2,{label},tile={cols}x{rows}:padding=3:margin=3:color=black"
    run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            src_rel,
            "-vf",
            vf,
            "-frames:v",
            "1",
            "-q:v",
            "3",
            out_rel,
        ],
        cwd=cwd,
    )
    return out_rel
