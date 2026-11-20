"""Chữ chuyển động cho ffmpeg (drawtext có biểu thức theo thời gian).

- Tiêu đề: hiện dần (mờ vào, trượt lên, phóng nhẹ), giữ, rồi mờ ra. Nền màu nhấn, chữ đậm nếu có font đậm.
- Phụ đề có lời: hiện từng từ (chữ chạy theo lời), căn trái, nền tối.

Dấu phẩy trong biểu thức phải escape thành \\, vì ffmpeg coi dấu phẩy là ngăn cách tham số.
Mọi đường dẫn là tương đối (font.ttf, texts/...), nên không có đường dẫn tuyệt đối trong lệnh.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

from .policy import Subtitle
from .spec import TextOverlay

ACCENT = "0xE8A87C"  # màu nhấn ấm; có thể đổi theo thương hiệu
_IN_S = 0.40  # thời gian hiện tiêu đề
_OUT_S = 0.30  # thời gian ẩn tiêu đề
_WORD_IN_S = 0.12  # thời gian hiện mỗi từ


def esc(expr: str) -> str:
    """Escape dấu phẩy để ffmpeg không tách tham số."""
    return expr.replace(",", "\\,")


def _p_in(start: float, dur: float) -> str:
    return f"clip((t-{start:.3f})/{dur:.2f},0,1)"


def _p_out(end: float, dur: float) -> str:
    return f"clip(({end:.3f}-t)/{dur:.2f},0,1)"


@dataclass(frozen=True)
class Style:
    width: int
    height: int
    font: str
    font_bold: str | None


def title_filter(i: int, t: TextOverlay, style: Style) -> str:
    h = style.height
    p_in = _p_in(t.start, _IN_S)
    p_out = _p_out(t.end, _OUT_S)
    base_y = {"top": f"{h * 0.10:.0f}", "center": "(h-text_h)/2", "bottom": f"{h * 0.70:.0f}"}[t.position]
    font = style.font_bold or style.font
    size = int(h * 0.046)
    fontsize = f"{size}*(1+0.10*(1-{p_in}))"
    alpha = f"min({p_in},{p_out})"
    y = f"{base_y}+46*(1-{p_in})"
    return (
        f"drawtext=fontfile={font}:textfile=texts/t{i}.txt:"
        f"fontsize={esc(fontsize)}:fontcolor=white:alpha={esc(alpha)}:"
        f"box=1:boxcolor={ACCENT}@0.92:boxborderw={int(h * 0.014)}:line_spacing=12:"
        f"x=(w-text_w)/2:y={esc(y)}:enable='between(t,{t.start:.3f},{t.end:.3f})'"
    )


def _wrap(text: str, vertical: bool) -> str:
    return "\n".join(textwrap.wrap(text, width=24 if vertical else 40)) or text


def word_reveal_times(sub: Subtitle) -> list[float]:
    """Mốc hiện của từng từ, tỉ lệ theo số ký tự để nhịp đọc tự nhiên."""
    words = sub.text.split()
    lengths = [len(w) + 1 for w in words]
    total = sum(lengths) or 1
    times, acc = [], 0
    for ln in lengths:
        times.append(sub.start + (sub.end - sub.start) * acc / total)
        acc += ln
    return times


def caption_variants(i: int, sub: Subtitle) -> list[tuple[float, float, str]]:
    """(từ, đến, tên file) cho từng bước hiện chữ. Hàm thuần: chỉ tính, không ghi file."""
    words = sub.text.split()
    times = word_reveal_times(sub)
    out = []
    for k in range(1, len(words) + 1):
        start = times[k - 1]
        end = times[k] if k < len(words) else sub.end
        out.append((start, end, f"texts/s{i}_{k}.txt"))
    return out


def write_caption_files(job_dir: Path, i: int, sub: Subtitle, vertical: bool) -> None:
    """Ghi nội dung từng bước hiện chữ đúng với tên file của caption_variants."""
    words = sub.text.split()
    for k in range(1, len(words) + 1):
        (job_dir / f"texts/s{i}_{k}.txt").write_text(_wrap(" ".join(words[:k]), vertical), encoding="utf-8")


def caption_filters(
    i: int, sub: Subtitle, style: Style, variants: list[tuple[float, float, str]]
) -> list[str]:
    h = style.height
    size = int(h * 0.034)
    filters = []
    for start, end, rel in variants:
        p_in = _p_in(start, _WORD_IN_S)
        filters.append(
            f"drawtext=fontfile={style.font}:textfile={rel}:fontsize={size}:fontcolor=white:"
            f"alpha={esc(p_in)}:box=1:boxcolor=black@0.55:boxborderw={int(h * 0.010)}:line_spacing=10:"
            f"x={int(style.width * 0.08)}:y={int(h * 0.80)}:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
    return filters
