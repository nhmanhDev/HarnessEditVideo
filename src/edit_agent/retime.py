"""Chỉnh đoạn cắt và dịch thời điểm chữ, lời đọc cho khớp: cắt rìa trống, tách tại ranh giới clip, bám điểm cắt.

Model viết kế hoạch với thời điểm chữ tính theo timeline lý tưởng. Khi harness rút ngắn một đoạn (rìa rèm trống,
vượt ranh giới clip), mọi thứ phía sau lệch đi. Module này tính lại thời điểm cho đúng cảnh đang chiếu.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Seg:
    orig: int  # chỉ số đoạn trong kế hoạch gốc
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


def empty_threshold(detail: list[tuple[float, float]], factor: float = 0.5) -> float:
    """Ngưỡng độ chi tiết dưới mức này coi là khung trống (rèm, tường)."""
    if not detail:
        return 0.0
    return factor * float(np.percentile([d for _, d in detail], 75))


def _detail_at(detail: list[tuple[float, float]], times: list[float], t: float) -> float:
    i = bisect.bisect_left(times, t)
    if i == 0:
        return detail[0][1]
    if i >= len(detail):
        return detail[-1][1]
    return detail[i][1] if abs(times[i] - t) < abs(times[i - 1] - t) else detail[i - 1][1]


def trim_empty_edges(
    start: float,
    end: float,
    detail: list[tuple[float, float]],
    thresh: float,
    max_trim: float = 1.0,
    step: float = 0.5,
    min_len: float = 1.2,
) -> tuple[float, float]:
    """Cắt bớt rìa đầu và cuối đoạn khi khung gần như trống, tối đa `max_trim` giây mỗi phía."""
    if not detail:
        return start, end
    times = [t for t, _ in detail]
    s, e, cut = start, end, 0.0
    while e - s - step >= min_len and cut < max_trim and _detail_at(detail, times, e - 0.25) < thresh:
        e -= step
        cut += step
    cut = 0.0
    while e - s - step >= min_len and cut < max_trim and _detail_at(detail, times, s + 0.25) < thresh:
        s += step
        cut += step
    return s, e


def split_indexed(
    items: list[tuple[int, float, float]], boundaries: list[float], min_len: float = 0.6
) -> tuple[list[Seg], list[str]]:
    """Cắt ngắn đoạn vượt ranh giới clip (giữ phần đầu); bỏ nếu phần còn lại quá ngắn. Giữ chỉ số đoạn gốc."""
    out: list[Seg] = []
    notes: list[str] = []
    for idx, start, end in items:
        new_end = end
        for b in sorted(boundaries):
            if start < b < new_end:
                new_end = b
        if new_end - start < min_len:
            notes.append(f"Bỏ đoạn {start:.1f}–{end:.1f}s: vượt ranh giới clip, phần còn lại quá ngắn")
            continue
        if new_end < end:
            notes.append(f"Cắt đoạn {start:.1f}–{end:.1f}s còn {start:.1f}–{new_end:.1f}s: không vượt ranh giới clip")
        out.append(Seg(idx, start, new_end))
    return out, notes


def offsets(lengths: list[float]) -> list[float]:
    acc, out = 0.0, []
    for ln in lengths:
        out.append(acc)
        acc += ln
    return out


def remap_time(t: float, planned: list[tuple[int, float]], actual: list[Seg], out_seconds: float) -> float:
    """Đổi thời điểm trên timeline kế hoạch sang timeline thực sau khi các đoạn bị rút ngắn hoặc bỏ.

    `planned` là [(chỉ số đoạn, độ dài kế hoạch)] theo thứ tự phát.
    """
    p_off = offsets([ln for _, ln in planned])
    a_len = {s.orig: s.length for s in actual}
    a_off = dict(zip((s.orig for s in actual), offsets([s.length for s in actual]), strict=True))
    for k, (idx, ln) in enumerate(planned):
        last = k == len(planned) - 1
        if p_off[k] <= t < p_off[k] + ln or last:
            if idx in a_off:
                return a_off[idx] + min(max(t - p_off[k], 0.0), a_len[idx])
            # Đoạn bị bỏ: chuyển tới đầu đoạn còn lại kế tiếp.
            for later_idx, _ in planned[k + 1 :]:
                if later_idx in a_off:
                    return a_off[later_idx]
            return out_seconds
    return min(t, out_seconds)


def snap(t: float, points: list[float], tol: float) -> float:
    """Bám vào điểm cắt gần nhất nếu cách không quá `tol` giây."""
    if not points:
        return t
    best = min(points, key=lambda p: abs(p - t))
    return best if abs(best - t) <= tol else t


def _level(series: list[tuple[float, float]], times: list[float], t0: float, t1: float) -> float:
    i0, i1 = bisect.bisect_left(times, t0), bisect.bisect_right(times, t1)
    vals = [d for _, d in series[i0:i1]] or [_detail_at(series, times, (t0 + t1) / 2)]
    return float(np.mean(vals))


def recenter(
    start: float,
    end: float,
    detail: list[tuple[float, float]],
    thresh: float,
    lo: float,
    hi: float,
    max_shift: float = 3.0,
    step: float = 0.25,
    motion: list[tuple[float, float]] | None = None,
    motion_ref: float = 3.0,
) -> tuple[float, float]:
    """Dịch cửa sổ [start, end] (giữ nguyên độ dài) trong khoảng [lo, hi] về chỗ MỌI khung đều có sản phẩm và đứng yên.

    Điểm của cửa sổ là mức hiện diện của khung xấu nhất trong cửa sổ, chia cho (1 + chuyển động lớn nhất /
    motion_ref). Một khung trống hoặc đang trượt là đủ để bị chê, nên xét khung xấu nhất chứ không phải trung bình.
    Khi điểm bằng nhau chọn dịch ít nhất; cửa sổ không đổi nếu không có chỗ tốt hơn.
    """
    if not detail:
        return start, end
    length = end - start
    times = [t for t, _ in detail]
    mtimes = [t for t, _ in motion] if motion else []

    def worst(series, stimes, s, pick):
        i0, i1 = bisect.bisect_left(stimes, s), bisect.bisect_right(stimes, s + length)
        vals = [v for _, v in series[i0:i1]] or [_detail_at(series, stimes, s + length / 2)]
        return pick(vals)

    def score(s: float) -> float:
        base = worst(detail, times, s, min)
        if motion:
            base = base / (1.0 + worst(motion, mtimes, s, max) / motion_ref)
        return base

    best_s, best = start, score(start)
    for k in range(1, int(max_shift / step) + 1):
        for s in (start - k * step, start + k * step):
            if s < lo or s + length > hi:
                continue
            sc = score(s)
            if sc > best + 1e-6:
                best_s, best = s, sc
    return best_s, best_s + length
