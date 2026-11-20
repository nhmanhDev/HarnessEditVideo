"""Dựng video bằng ffmpeg từ kế hoạch đã kiểm tra.

Mọi đường dẫn trong lệnh ffmpeg là đường dẫn tương đối so với thư mục job (ffmpeg chạy với cwd = thư mục job),
nên không có đường dẫn tuyệt đối nào đi vào lệnh hay file đồ thị.
"""

from __future__ import annotations

import shutil
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from . import motion
from .media import run
from .policy import Piece, Subtitle
from .spec import TextOverlay


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
    font_bold_file: str | None = None  # font đậm cho tiêu đề, nếu có
    overlay_file: str | None = None  # lớp chữ chuyển động WebM trong suốt (HyperFrames); thay cho drawtext
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
    font = job.font_file or "font.ttf"
    style = motion.Style(
        width=job.width,
        height=job.height,
        font=font,
        font_bold=job.font_bold_file,
    )
    filters: list[str] = []
    if job.overlay_file:
        # Lớp chữ chuyển động dựng sẵn (WebM trong suốt) là đầu vào cuối cùng, sau nhạc và các lời đọc.
        overlay_index = 1 + (1 if job.music_file else 0) + len(job.voice_files)
        parts.append(f"[{current}][{overlay_index}:v]overlay=0:0:format=auto[ovhf]")
        current = "ovhf"
    else:
        for i, t in enumerate(job.texts):
            filters.append(motion.title_filter(i, t, style))
        for i, s in enumerate(job.subtitles):
            filters.extend(motion.caption_filters(i, s, style, motion.caption_variants(i, s)))
    for k, f in enumerate(filters):
        nxt = f"ov{k}"
        parts.append(f"[{current}]{f}[{nxt}]")
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
            # Cắt đoạn lặng ở đầu bài nhạc để video không im lặng ngay khi mở đầu.
            f"silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB,"
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
        plain = t.text.replace("*", "")  # bỏ dấu * đánh dấu từ nhấn khi dùng chữ drawtext dự phòng
        (job_dir / "texts" / f"t{i}.txt").write_text(_wrap(plain, vertical), encoding="utf-8")
    for i, s in enumerate(job.subtitles):
        motion.write_caption_files(job_dir, i, s, vertical)


def render(
    ffmpeg: str,
    job_dir: Path,
    job: RenderJob,
    font_src: Path | None,
    font_bold_src: Path | None = None,
) -> Path:
    if font_src is not None and job.font_file is None:
        shutil.copy2(font_src, job_dir / "font.ttf")
        job.font_file = "font.ttf"
    if font_bold_src is not None and job.font_bold_file is None:
        shutil.copy2(font_bold_src, job_dir / "font_bold.ttf")
        job.font_bold_file = "font_bold.ttf"
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
    if job.overlay_file:
        # WebM có alpha phải giải mã bằng libvpx-vp9 mới giữ được kênh trong suốt.
        inputs += ["-c:v", "libvpx-vp9", "-i", job.overlay_file]

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
