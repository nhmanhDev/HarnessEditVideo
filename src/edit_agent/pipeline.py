"""Luồng dựng video tách hai bước, để ai lập kế hoạch cũng được:

1. prepare: nhận video, đo thông số, nhận dạng lời, lấy khung hình, viết packet.md.
2. render:  đọc plan.json (model hoặc người viết), kiểm quy tắc, tạo lời đọc, dựng, ghi báo cáo.

run = prepare + lập kế hoạch bằng Claude + render.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .clips import combine_clips
from .config import Settings, require_tool
from .intake import fetch_folder, fetch_source, is_folder_input, new_job_dir
from .media import Probe, extract_audio_wav, extract_frames, probe
from .motion_hf import render_overlay
from .music import Track, load_tracks
from .planner import build_packet, plan_edit
from .policy import PolicyResult, Span, apply_policy, speech_spans, uncovered_seconds
from .render import RenderJob, render
from .select import analyze_frames, motion_scores, pick_windows, presence_scores
from .spec import EditPlan, JobSpec
from .transcribe import TranscriptSegment, transcribe
from .tts import make_provider


@dataclass
class JobContext:
    job_dir: Path
    spec: JobSpec
    src_rel: str
    info: Probe
    transcript: list[TranscriptSegment]
    speech: list[Span]
    frames: list[tuple[float, Path]]
    clips: list[dict] = field(default_factory=list)  # [{index, name, start, end}] trong video nguồn gộp


@dataclass
class RunResult:
    job_dir: Path
    output: Path
    plan: EditPlan
    warnings: list[str] = field(default_factory=list)


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_anthropic_client():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError(
            "Thiếu ANTHROPIC_API_KEY. Dùng --planner manual và viết plan.json, hoặc đặt khóa trong .env."
        )
    import anthropic

    return anthropic.Anthropic(api_key=key)


def prepare(settings: Settings, spec: JobSpec) -> JobContext:
    ffmpeg = require_tool(settings.ffmpeg)
    ffprobe = require_tool(settings.ffprobe)

    label = "drive" if spec.input.startswith("http") else Path(spec.input).stem
    job_dir = new_job_dir(settings, label)
    _write_json(job_dir / "spec.json", spec.model_dump(mode="json"))

    clips: list[dict] | None = None
    if is_folder_input(spec.input):
        # Thư mục nhiều clip: gộp thành một video nguồn, ghi lại ranh giới từng clip.
        src = job_dir / "input" / "source.mp4"
        clips = combine_clips(ffmpeg, ffprobe, fetch_folder(spec.input, job_dir), src, job_dir / "input" / "norm")
    else:
        src = fetch_source(spec.input, job_dir)
    info = probe(ffprobe, src)
    if clips is None:
        name = "clip" if spec.input.startswith("http") else Path(spec.input).name
        clips = [{"index": 0, "name": name, "start": 0.0, "end": round(info.duration, 3)}]
    _write_json(job_dir / "clips.json", clips)
    _write_json(
        job_dir / "probe.json",
        {"duration": info.duration, "width": info.width, "height": info.height, "has_audio": info.has_audio},
    )

    transcript: list[TranscriptSegment] = []
    if info.has_audio:
        wav = extract_audio_wav(ffmpeg, src, job_dir / "audio.wav")
        transcript = transcribe(wav, settings.whisper_model, spec.language)
    _write_json(job_dir / "transcript.json", [t.to_dict() for t in transcript])
    speech = speech_spans(transcript)

    frames = extract_frames(ffmpeg, src, job_dir / "frames", info.duration)
    _write_json(job_dir / "frames.json", [{"t": round(t, 2), "file": f.name} for t, f in frames])

    # Đoạn gợi ý: nhiều chi tiết, khác nhau về hình. Đưa cho model để tránh khung trống và cảnh lặp.
    scores, sigs = analyze_frames(ffmpeg, src, info.duration)
    boundaries = [c["end"] for c in clips[:-1]]
    # Độ lệch so với phông của từng clip: cao = có sản phẩm trong khung. Dùng để chọn đoạn gợi ý và cắt rìa khung trống.
    presence = presence_scores(scores, sigs, boundaries)
    _write_json(job_dir / "detail.json", [[round(t, 2), round(s, 3)] for t, s in presence])
    # Chuyển động theo thời gian: để dịch cửa sổ về lúc sản phẩm đã yên vị, không phải lúc đang trượt vào hoặc ra.
    _write_json(job_dir / "motion.json", [[round(t, 2), round(m, 3)] for t, m in motion_scores(scores, sigs)])
    np.save(job_dir / "sigs.npy", sigs)
    wins = pick_windows(presence, min(30, max(10, 2 * len(clips))), 2.2, info.duration, sigs=sigs, min_diff=8.0)
    # Đoạn gợi ý không được vượt ranh giới clip.
    candidates = [w.to_dict() for w in wins if not any(w.start < b < w.end for b in boundaries)]
    _write_json(job_dir / "candidates.json", candidates)

    tracks = load_tracks(settings.music_dir)
    (job_dir / "packet.md").write_text(
        build_packet(spec, info.duration, speech, transcript, sorted(tracks), candidates, clips),
        encoding="utf-8",
    )

    return JobContext(
        job_dir=job_dir,
        spec=spec,
        src_rel=f"input/{src.name}",
        info=info,
        transcript=transcript,
        speech=speech,
        frames=frames,
        clips=clips,
    )


def load_context(job_dir: Path) -> JobContext:
    spec = JobSpec.model_validate_json((job_dir / "spec.json").read_text(encoding="utf-8"))
    pr = json.loads((job_dir / "probe.json").read_text(encoding="utf-8"))
    info = Probe(duration=pr["duration"], width=pr["width"], height=pr["height"], has_audio=pr["has_audio"])
    transcript = [TranscriptSegment(**t) for t in json.loads((job_dir / "transcript.json").read_text(encoding="utf-8"))]
    frame_index = json.loads((job_dir / "frames.json").read_text(encoding="utf-8"))
    frames = [(f["t"], job_dir / "frames" / f["file"]) for f in frame_index]
    src = next((job_dir / "input").glob("source.*"))
    clips_file = job_dir / "clips.json"
    clips = json.loads(clips_file.read_text(encoding="utf-8")) if clips_file.exists() else []
    return JobContext(
        job_dir=job_dir,
        spec=spec,
        src_rel=f"input/{src.name}",
        info=info,
        transcript=transcript,
        speech=speech_spans(transcript),
        frames=frames,
        clips=clips,
    )


def plan_with_model(settings: Settings, ctx: JobContext) -> EditPlan:
    tracks = load_tracks(settings.music_dir)
    client = _make_anthropic_client()
    plan = plan_edit(
        client,
        settings.edit_model,
        ctx.spec,
        ctx.info.duration,
        ctx.speech,
        ctx.transcript,
        ctx.frames,
        sorted(tracks),
    )
    _write_json(ctx.job_dir / "plan.raw.json", plan.model_dump(mode="json"))
    return plan


def render_plan(settings: Settings, ctx: JobContext, plan: EditPlan) -> RunResult:
    ffmpeg = require_tool(settings.ffmpeg)
    job_dir = ctx.job_dir
    tracks = load_tracks(settings.music_dir)
    boundaries = [c["end"] for c in ctx.clips[:-1]]
    detail_file = ctx.job_dir / "detail.json"
    detail = [(t, s) for t, s in json.loads(detail_file.read_text(encoding="utf-8"))] if detail_file.exists() else None
    motion_file = ctx.job_dir / "motion.json"
    motion = [(t, m) for t, m in json.loads(motion_file.read_text(encoding="utf-8"))] if motion_file.exists() else None
    sigs_file = ctx.job_dir / "sigs.npy"
    sigs = np.load(sigs_file) if sigs_file.exists() else None
    policy: PolicyResult = apply_policy(
        ctx.spec, plan, ctx.transcript, ctx.info.duration, set(tracks), boundaries, detail, motion, sigs
    )

    voice_files: list[tuple[float, str]] = []
    if policy.voice_lines:
        provider = make_provider(settings.tts_provider, settings.tts_voice)
        for line in policy.voice_lines:
            # Bộ nhớ đệm theo giọng và nội dung: vòng dựng lại không phải tạo lại lời đọc.
            key = hashlib.sha1(f"{settings.tts_voice}|{line.text}".encode()).hexdigest()[:12]
            rel = f"voice/{key}.mp3"
            if not (job_dir / rel).exists():
                provider.synthesize(line.text, job_dir / rel)
            voice_files.append((line.start, rel))

    # Không có tiếng gốc và không có lời đọc: video sẽ im lặng. Khi đó tự đặt nhạc nền từ kho có giấy phép.
    # Thiếu tiếng = có khoảng không có lời quá 1 giây (kể cả đoạn cuối video).
    needs_bed = (not policy.keep_audio) and uncovered_seconds(policy.voice_lines, policy.output_seconds) > 1.0
    if needs_bed and not policy.plan.music.track and tracks:
        auto = sorted(tracks)[0]
        policy.plan = policy.plan.model_copy(update={"music": policy.plan.music.model_copy(update={"track": auto})})
        policy.warnings.append(f"Có khoảng không lời quá 1 giây: tự đặt nhạc nền '{auto}' từ kho có giấy phép")

    music_rel: str | None = None
    if policy.plan.music.track:
        track: Track = tracks[policy.plan.music.track]
        music_rel = f"music/{track.id}{track.file.suffix}"
        (job_dir / "music").mkdir(exist_ok=True)
        shutil.copy2(track.file, job_dir / music_rel)

    # Chữ chuyển động: ưu tiên lớp HyperFrames (đẹp hơn); lỗi thì dùng chữ ffmpeg dự phòng.
    overlay_rel: str | None = None
    if settings.motion_engine == "hyperframes" and (policy.plan.texts or policy.subtitles):
        overlay_rel = render_overlay(
            job_dir,
            policy.plan.texts,
            policy.subtitles,
            policy.output_seconds,
            ctx.spec.width,
            ctx.spec.height,
            ctx.spec.fps,
        )
        if overlay_rel is None:
            policy.warnings.append("Không dựng được lớp chữ HyperFrames: dùng chữ ffmpeg dự phòng")

    job = RenderJob(
        source=ctx.src_rel,
        pieces=policy.pieces,
        output_seconds=policy.output_seconds,
        width=ctx.spec.width,
        height=ctx.spec.height,
        fps=ctx.spec.fps,
        keep_audio=policy.keep_audio,
        texts=policy.plan.texts,
        subtitles=policy.subtitles,
        voice_files=voice_files,
        music_file=music_rel,
        music_volume=policy.plan.music.volume,
        output="final.mp4",
        fit=ctx.spec.fit,
        overlay_file=overlay_rel,
    )
    output = render(ffmpeg, job_dir, job, settings.font_file, settings.font_bold)

    _write_json(job_dir / "plan.json", policy.plan.model_dump(mode="json"))
    # Điểm cắt theo kế hoạch trên timeline đầu ra; QA dùng để đếm nhịp cắt chính xác.
    _write_json(job_dir / "cuts.json", [round(p.out_offset, 3) for p in policy.pieces[1:]])
    _write_report(job_dir, ctx.spec, ctx.info.duration, policy, tracks)
    return RunResult(job_dir=job_dir, output=output, plan=policy.plan, warnings=policy.warnings)


def run_job(settings: Settings, spec: JobSpec, plan_override: EditPlan | None = None) -> RunResult:
    ctx = prepare(settings, spec)
    plan = plan_override if plan_override is not None else plan_with_model(settings, ctx)
    return render_plan(settings, ctx, plan)


def _write_report(job_dir: Path, spec: JobSpec, src_duration: float, policy: PolicyResult, tracks: dict) -> None:
    lines = [
        f"# Báo cáo job {job_dir.name}",
        "",
        f"- Loại: {spec.job_type.value}",
        f"- Video nguồn: {src_duration:.1f}s",
        f"- Video đầu ra: {policy.output_seconds:.1f}s",
        f"- Giữ tiếng gốc: {'có' if policy.keep_audio else 'không'}",
        f"- Lời đọc: {len(policy.voice_lines)}",
        f"- Phụ đề: {len(policy.subtitles)} dòng",
    ]
    track_id = policy.plan.music.track
    if track_id:
        t = tracks[track_id]
        lines.append(f"- Nhạc: {t.id}, giấy phép: {t.license}, nguồn: {t.source}")
    else:
        lines.append("- Nhạc: không dùng")
    if policy.warnings:
        lines += ["", "## Cảnh báo kiểm quy tắc"] + [f"- {w}" for w in policy.warnings]
    if policy.plan.notes:
        lines += ["", "## Ghi chú của agent", policy.plan.notes]
    (job_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def plan_from_file(path: Path) -> EditPlan:
    return EditPlan.model_validate(json.loads(path.read_text(encoding="utf-8")))
