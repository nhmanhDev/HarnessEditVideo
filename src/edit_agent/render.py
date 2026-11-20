"""Dựng video bằng ffmpeg từ kế hoạch đã kiểm tra.

Mọi đường dẫn trong lệnh ffmpeg là đường dẫn tương đối so với thư mục job (ffmpeg chạy với cwd = thư mục job),
nên không có đường dẫn tuyệt đối nào đi vào lệnh hay file đồ thị.
"""

from __future__ import annotations

import shutil
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from .media import run
from .policy import Piece, Subtitle
from .spec import TextOverlay

_POS_Y = {"top": "h*0.08", "center": "(h-text_h)/2", "bottom": "h*0.72"}
_SUB_Y = "h*0.84"


@dataclass
class RenderJob:
    """Mọi đầu vào của bước dựng, đều tính từ thư mục job."""

    source: str  # ví dụ input/source.mp4
    pieces: list[Piece]
    output_seconds: float
    width: int
    height: int
    fps: int
    keep_audio: bool
    texts: list[TextOverlay] = field(default_factory=list)
    subtitles: list[Subtitle] = field(default_factory=list)
    voice_files: list[tuple[float, str]] = field(default_factory=list)  # (thời điểm ra, file tương đối)
    music_file: str | None = None
    music_volume: float = 0.25
    font_file: str | None = None  # ví dụ font.ttf
    output: str = "final.mp4"
    # "blur": giữ toàn bộ khung, nền mờ (không mất hai bên khi cắt từ video ngang). "crop": lấp đầy, cắt bớt.
    fit: str = "blur"
    # Âm lượng giao (LUFS tích hợp). None = không chuẩn hoá. Reel mẫu đạt đều ở -14.
    loudness_lufs: float | None = -14.0
    music_fade_in_s: float = 0.5
    music_fade_out_s: float = 1.5


def _wrap(text: str, vertical: bool) -> str:
    return "\n".join(textwrap.wrap(text, width=22 if vertical else 40)) or text


def _overlay_label(i: int) -> str:
    return f"txt{i}"


def build_filter_graph(job: RenderJob) -> tuple[str, str | None, str | None]:
    """Trả về (đồ thị, nhãn video đầu ra, nhãn âm thanh đầu ra hoặc None)."""
    parts: list[str] = []
    n = len(job.pieces)

    for i, p in enumerate(job.pieces):
        trim = f"[0:v]trim=start={p.src_start:.3f}:end={p.src_end:.3f},setpts=PTS-STARTPTS"
        if job.fit == "blur":
            # Nền: phóng to lấp khung rồi làm mờ. Lớp trước: cả khung nguồn, vừa chiều rộng, đặt giữa.
            parts.append(
                f"{trim},split=2[bgs{i}][fgs{i}];"
                f"[bgs{i}]scale={job.width}:{job.height}:force_original_aspect_ratio=increase,"
                f"crop={job.width}:{job.height},boxblur=24:2[bg{i}];"
                f"[fgs{i}]scale={job.width}:-2[fg{i}];"
                f"[bg{i}][fg{i}]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={job.fps}[v{i}]"
            )
        else:
            parts.append(
                f"{trim},scale={job.width}:{job.height}:force_original_aspect_ratio=increase,"
                f"crop={job.width}:{job.height},setsar=1,fps={job.fps}[v{i}]"
            )
    parts.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]")

    current = "vc"
    overlays: list[tuple[str, str, str, str]] = []  # (nhãn file, vị trí, cỡ chữ, mốc thời gian)
    font = job.font_file or "font.ttf"
    for i, t in enumerate(job.texts):
        overlays.append(
            (
                f"texts/t{i}.txt",
                _POS_Y[t.position],
                str(int(job.height * 0.042)),
                f"{t.start:.3f}|{t.end:.3f}",
            )
        )
    for i, s in enumerate(job.subtitles):
        overlays.append(
            (f"texts/s{i}.txt", _SUB_Y, str(int(job.height * 0.032)), f"{s.start:.3f}|{s.end:.3f}")
        )

    for k, (textfile, ypos, size, window) in enumerate(overlays):
        start, end = window.split("|")
        nxt = f"ov{k}"
        parts.append(
            f"[{current}]drawtext=fontfile={font}:textfile={textfile}:fontsize={size}:fontcolor=white:"
            f"box=1:boxcolor=black@0.45:boxborderw=22:line_spacing=8:x=(w-text_w)/2:y={ypos}:"
            f"enable='between(t,{start},{end})'[{nxt}]"
        )
        current = nxt
    video_label = current

    # Âm thanh. Thứ tự đầu vào: 0 = nguồn, 1 = nhạc (nếu có), sau đó là các file lời đọc.
    music_index = 1 if job.music_file else None
    input_index = 2 if job.music_file else 1
    audio_parts: list[str] = []
    speech_label: str | None = None
    if job.keep_audio:
        for i, p in enumerate(job.pieces):
            audio_parts.append(
                f"[0:a]atrim=start={p.src_start:.3f}:end={p.src_end:.3f},asetpts=PTS-STARTPTS[a{i}]"
            )
        audio_parts.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[aorig]")
        speech_label = "aorig"

    voice_labels: list[str] = []
    for k, (start_s, _file) in enumerate(job.voice_files):
        ms = int(round(start_s * 1000))
        label = f"vo{k}"
        audio_parts.append(
            f"[{input_index}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            f"adelay={ms}|{ms}[{label}]"
        )
        voice_labels.append(label)
        input_index += 1
    if voice_labels:
        audio_parts.append(
            "".join(f"[{v}]" for v in voice_labels)
            + (
                f"amix=inputs={len(voice_labels)}:duration=longest:normalize=0[voice]"
                if len(voice_labels) > 1
                else "anull[voice]"
            )
        )
        if speech_label:
            audio_parts.append(f"[{speech_label}][voice]amix=inputs=2:duration=longest:normalize=0[speech]")
            speech_label = "speech"
        else:
            speech_label = "voice"

    music_label: str | None = None
    if music_index is not None:
        out_end = max(0.0, job.output_seconds - job.music_fade_out_s)
        audio_parts.append(
            f"[{music_index}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            f"atrim=0:{job.output_seconds:.3f},asetpts=PTS-STARTPTS,volume={job.music_volume:.3f},"
            f"afade=t=in:st=0:d={job.music_fade_in_s:.2f},"
            f"afade=t=out:st={out_end:.3f}:d={job.music_fade_out_s:.2f}[mus]"
        )
        music_label = "mus"

    final_audio: str | None = None
    if speech_label and music_label:
        audio_parts.append(f"[{speech_label}]asplit=2[sc][sp]")
        audio_parts.append("[mus][sc]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=350[musd]")
        audio_parts.append("[sp][musd]amix=inputs=2:duration=longest:normalize=0[mix]")
        final_audio = "mix"
    elif speech_label:
        final_audio = speech_label
    elif music_label:
        final_audio = music_label

    if final_audio:
        loud = ""
        if job.loudness_lufs is not None:
            # Chuẩn giao: âm lượng tích hợp theo LUFS, đỉnh thực -1,5 dBTP để không xén khi nén lại.
            loud = f",loudnorm=I={job.loudness_lufs:.1f}:TP=-1.5:LRA=11"
        audio_parts.append(
            f"[{final_audio}]atrim=0:{job.output_seconds:.3f},asetpts=PTS-STARTPTS{loud}[afinal]"
        )
        final_audio = "afinal"

    graph = ";\n".join(parts + audio_parts)
    return graph, video_label, final_audio


def write_overlay_texts(job_dir: Path, job: RenderJob) -> None:
    (job_dir / "texts").mkdir(parents=True, exist_ok=True)
    vertical = job.height >= job.width
    for i, t in enumerate(job.texts):
        (job_dir / "texts" / f"t{i}.txt").write_text(_wrap(t.text, vertical), encoding="utf-8")
    for i, s in enumerate(job.subtitles):
        (job_dir / "texts" / f"s{i}.txt").write_text(_wrap(s.text, vertical), encoding="utf-8")


def render(ffmpeg: str, job_dir: Path, job: RenderJob, font_src: Path | None) -> Path:
    if font_src is not None and job.font_file is None:
        shutil.copy2(font_src, job_dir / "font.ttf")
        job.font_file = "font.ttf"
    if (job.texts or job.subtitles) and not job.font_file:
        raise RuntimeError("Thiếu font có dấu tiếng Việt. Đặt FONT_FILE trong .env.")

    write_overlay_texts(job_dir, job)
    graph, video_label, audio_label = build_filter_graph(job)
    (job_dir / "graph.txt").write_text(graph, encoding="utf-8")

    inputs = ["-i", job.source]
    if job.music_file:
        inputs += ["-stream_loop", "-1", "-i", job.music_file]
    for _start, f in job.voice_files:
        inputs += ["-i", f]

    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        *inputs,
        "-filter_complex",
        graph,
        "-map",
        f"[{video_label}]",
    ]
    if audio_label:
        cmd += ["-map", f"[{audio_label}]", "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]
    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(job.fps),
        "-movflags",
        "+faststart",
        "-t",
        f"{job.output_seconds:.3f}",
        job.output,
    ]
    run(cmd, cwd=job_dir)
    return job_dir / job.output
