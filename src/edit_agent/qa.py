"""Kiểm chất lượng bằng số đo: âm lượng, đỉnh, im lặng, khung đen, đứng hình, nhịp cắt.

Ngưỡng lấy từ mẫu reel đạt (workspace/qa/refs.json) và chuẩn giao -14 LUFS. Đo, không cảm tính.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import Settings, require_tool
from .media import probe, run
from .profile import scene_cuts, shot_lengths

_I = re.compile(r"\bI:\s+(-?\d+(?:\.\d+)?)\s+LUFS")
_LRA = re.compile(r"\bLRA:\s+(-?\d+(?:\.\d+)?)\s+LU")
_PEAK = re.compile(r"\bPeak:\s+(-?\d+(?:\.\d+)?)\s+dBFS")
_BLACK = re.compile(r"black_start:(\d+(?:\.\d+)?)\s+black_end:(\d+(?:\.\d+)?)")
_FREEZE = re.compile(r"freeze_start: (\d+(?:\.\d+)?)")
_FREEZE_END = re.compile(r"freeze_end: (\d+(?:\.\d+)?)")
_SILENCE = re.compile(r"silence_start: (-?\d+(?:\.\d+)?)")
_SILENCE_END = re.compile(r"silence_end: (\d+(?:\.\d+)?)")


@dataclass
class Measure:
    file: str
    duration: float
    width: int
    height: int
    has_audio: bool
    lufs_integrated: float | None = None
    lra: float | None = None
    true_peak_dbfs: float | None = None
    silence_s: float = 0.0
    black_s: float = 0.0
    freeze_count: int = 0
    freeze_max_s: float = 0.0
    cuts: int = 0
    cuts_per_10s: float = 0.0
    shot_median_s: float | None = None
    shot_max_s: float | None = None
    checks: dict[str, bool] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _last(pattern: re.Pattern, text: str) -> float | None:
    found = pattern.findall(text)
    return float(found[-1]) if found else None


def measure(settings: Settings, video: Path) -> Measure:
    ffmpeg = require_tool(settings.ffmpeg)
    ffprobe = require_tool(settings.ffprobe)
    info = probe(ffprobe, video)
    m = Measure(
        file=video.name,
        duration=round(info.duration, 2),
        width=info.width,
        height=info.height,
        has_audio=info.has_audio,
    )

    if info.has_audio:
        ebu = run(
            [
                ffmpeg,
                "-hide_banner",
                "-nostats",
                "-i",
                str(video),
                "-af",
                "ebur128=peak=true",
                "-f",
                "null",
                "-",
            ]
        )
        m.lufs_integrated = _last(_I, ebu.stderr)
        m.lra = _last(_LRA, ebu.stderr)
        m.true_peak_dbfs = _last(_PEAK, ebu.stderr)
        sil = run(
            [
                ffmpeg,
                "-hide_banner",
                "-nostats",
                "-i",
                str(video),
                "-af",
                "silencedetect=n=-45dB:d=1",
                "-f",
                "null",
                "-",
            ]
        )
        starts = [float(x) for x in _SILENCE.findall(sil.stderr)]
        ends = [float(x) for x in _SILENCE_END.findall(sil.stderr)]
        m.silence_s = round(sum((e - s) for s, e in zip(starts, ends, strict=False)), 2)

    blk = run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-vf",
            "blackdetect=d=0.25:pix_th=0.10",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    blacks = [(float(a), float(b)) for a, b in _BLACK.findall(blk.stderr)]
    # Khung đen cuối video (thẻ kết) không tính là lỗi.
    body = [(a, b) for a, b in blacks if b < info.duration - 0.2]
    m.black_s = round(sum(b - a for a, b in body), 2)

    frz = run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-vf",
            "freezedetect=n=0.003:d=1.0",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    fstarts = [float(x) for x in _FREEZE.findall(frz.stderr)]
    fends = [float(x) for x in _FREEZE_END.findall(frz.stderr)]
    lengths = [e - s for s, e in zip(fstarts, fends, strict=False)]
    m.freeze_count = len(lengths)
    m.freeze_max_s = round(max(lengths), 2) if lengths else 0.0

    planned = video.parent / "cuts.json"
    if planned.exists():
        # Điểm cắt do pipeline ghi lại: chính xác hơn bộ phát hiện đổi cảnh.
        import json

        cuts = [float(x) for x in json.loads(planned.read_text(encoding="utf-8"))]
    else:
        cuts = scene_cuts(ffmpeg, video)
    m.cuts = len(cuts)
    m.cuts_per_10s = round(len(cuts) / info.duration * 10, 2) if info.duration else 0.0
    lens = shot_lengths(cuts, info.duration)
    if lens:
        m.shot_median_s = round(statistics.median(lens), 2)
        m.shot_max_s = max(lens)
    return m


# Ngưỡng hiệu chỉnh từ 6 reel mẫu đạt (đo 2026-11-20, xem workspace/qa/refs.json):
# - âm lượng: cả 6 reel đạt -14,0 đến -14,1 LUFS.
# - đỉnh thực: 6 reel từ -0,5 đến -3,9 dBTP, nên ngưỡng chỉ chặn vượt 0 dBTP (xén).
# - đứng hình: reel đạt có tới 1,6 giây (giữ hình sản phẩm), nên ngưỡng 2 giây.
# - nhịp cắt: trung vị 1,6 đến 3,5 giây với reel có nhiều cảnh; chỉ cảnh báo.
THRESHOLDS = {
    "lufs_min": -16.0,
    "lufs_max": -12.0,
    "true_peak_max": -0.1,
    "silence_max_s": 1.0,
    "black_max_s": 0.5,
    "freeze_max_s": 2.0,
    "shot_median_min": 1.2,
    "shot_median_max": 3.5,
    "shot_max_max": 6.0,
}


def judge(m: Measure, expect_audio: bool) -> Measure:
    t = THRESHOLDS
    checks: dict[str, bool] = {}
    fails: list[str] = []

    def ok(name: str, cond: bool, msg: str) -> None:
        checks[name] = cond
        if not cond:
            fails.append(msg)

    ok("resolution_9x16", m.height > m.width and m.width >= 540, f"khung {m.width}x{m.height} không phải dọc")
    if expect_audio:
        ok("has_audio", m.has_audio, "không có âm thanh")
    if m.has_audio and m.lufs_integrated is not None:
        ok(
            "loudness",
            t["lufs_min"] <= m.lufs_integrated <= t["lufs_max"],
            f"âm lượng {m.lufs_integrated} LUFS ngoài {t['lufs_min']}..{t['lufs_max']}",
        )
        ok(
            "true_peak",
            (m.true_peak_dbfs or -99) <= t["true_peak_max"],
            f"đỉnh {m.true_peak_dbfs} dBTP vượt {t['true_peak_max']}",
        )
        ok("silence", m.silence_s <= t["silence_max_s"], f"im lặng {m.silence_s}s")
    ok("black", m.black_s <= t["black_max_s"], f"khung đen {m.black_s}s")
    ok("freeze", m.freeze_max_s <= t["freeze_max_s"], f"đứng hình {m.freeze_max_s}s")
    # Nhịp cắt chỉ là cảnh báo: video một cảnh (người nói liền mạch) không phải lỗi.
    warns: list[str] = []
    if m.shot_median_s is not None and m.cuts >= 3:
        if not (t["shot_median_min"] <= m.shot_median_s <= t["shot_median_max"]):
            warns.append(f"cảnh trung vị {m.shot_median_s}s ngoài dải 1,2–3,5s")
        if (m.shot_max_s or 0) > t["shot_max_max"]:
            warns.append(f"cảnh dài nhất {m.shot_max_s}s")
    m.checks = checks
    m.failures = fails
    m.warnings = warns
    return m
