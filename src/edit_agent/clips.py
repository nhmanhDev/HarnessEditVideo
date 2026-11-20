"""Nhiều clip thành một nguồn: gộp các clip trong thư mục (Drive hoặc máy) thành một video nguồn duy nhất.

Mỗi clip được chuẩn hoá (rộng tối đa 1440, 30 khung hình/giây, có âm thanh, thiếu thì thêm im lặng) rồi nối liền.
Bản gộp chỉ cần rộng 1440 vì video đầu ra rộng 1440; không mất chất lượng so với nguồn 4K.
Trả về danh sách clip kèm mốc bắt đầu và kết thúc trong video gộp, để các đoạn cắt không vượt qua ranh giới clip.
"""

from __future__ import annotations

import re
from pathlib import Path

from .media import probe, run

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"}


def _natural_key(path: Path) -> list:
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", path.name)]


def list_videos(folder: Path) -> list[Path]:
    return sorted((p for p in folder.rglob("*") if p.suffix.lower() in VIDEO_EXTS and p.is_file()), key=_natural_key)


def combine_clips(
    ffmpeg: str,
    ffprobe: str,
    clips: list[Path],
    out: Path,
    work: Path,
    max_width: int = 1440,
    fps: int = 30,
) -> list[dict]:
    """Chuẩn hoá và nối các clip thành `out`. Trả về [{index, name, start, end}] trong video gộp."""
    work.mkdir(parents=True, exist_ok=True)
    norm_names: list[str] = []
    meta: list[dict] = []
    for i, clip in enumerate(clips):
        info = probe(ffprobe, clip)
        name = f"clip_{i:02d}.mp4"
        vf = f"scale='min({max_width},iw)':-2,setsar=1,fps={fps}"
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(clip)]
        if info.has_audio:
            cmd += ["-vf", vf, "-c:a", "aac", "-ar", "44100", "-ac", "2"]
        else:
            # Clip không có tiếng: thêm đoạn im lặng cùng độ dài để nối được với clip có tiếng.
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-vf", vf, "-shortest", "-c:a", "aac"]
        cmd += [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            str(work / name),
        ]
        run(cmd)
        norm_names.append(name)
        meta.append({"index": i, "name": clip.name})

    listing = "\n".join(f"file '{n}'" for n in norm_names) + "\n"
    (work / "list.txt").write_text(listing, encoding="utf-8")
    run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            "list.txt",
            "-c",
            "copy",
            str(out.resolve()),
        ],
        cwd=work,
    )

    offset = 0.0
    for m, n in zip(meta, norm_names, strict=True):
        dur = probe(ffprobe, work / n).duration
        m["start"] = round(offset, 3)
        m["end"] = round(offset + dur, 3)
        offset += dur
    return meta


def split_at_boundaries(
    segments: list[tuple[float, float]], boundaries: list[float], min_len: float = 0.6
) -> tuple[list[tuple[float, float]], list[str]]:
    """Cắt ngắn đoạn vượt ranh giới clip (giữ phần đầu); bỏ nếu phần còn lại quá ngắn."""
    out: list[tuple[float, float]] = []
    notes: list[str] = []
    for start, end in segments:
        new_end = end
        for b in sorted(boundaries):
            if start < b < new_end:
                new_end = b
        if new_end - start < min_len:
            notes.append(f"Bỏ đoạn {start:.1f}–{end:.1f}s: vượt ranh giới clip, phần còn lại quá ngắn")
            continue
        if new_end < end:
            notes.append(f"Cắt đoạn {start:.1f}–{end:.1f}s còn {start:.1f}–{new_end:.1f}s: không vượt ranh giới clip")
        out.append((start, new_end))
    return out, notes
