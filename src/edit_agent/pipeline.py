"""Luồng dựng video tách hai bước, để ai lập kế hoạch cũng được:

1. prepare: nhận video, đo thông số, nhận dạng lời, lấy khung hình, viết packet.md.
2. render:  đọc plan.json (model hoặc người viết), kiểm quy tắc, tạo lời đọc, dựng, ghi báo cáo.

run = prepare + lập kế hoạch bằng Claude + render.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings, require_tool
from .intake import fetch_source, new_job_dir
from .media import Probe, extract_audio_wav, extract_frames, probe
from .music import Track, load_tracks
from .planner import build_packet, plan_edit
from .policy import PolicyResult, Span, apply_policy, speech_spans
from .render import RenderJob, render
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

    src = fetch_source(spec.input, job_dir)
    info = probe(ffprobe, src)
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

    tracks = load_tracks(settings.music_dir)
    (job_dir / "packet.md").write_text(
        build_packet(spec, info.duration, speech, transcript, sorted(tracks)), encoding="utf-8"
    )

    return JobContext(
        job_dir=job_dir,
        spec=spec,
        src_rel=f"input/{src.name}",
        info=info,
        transcript=transcript,
        speech=speech,
        frames=frames,
    )


def load_context(job_dir: Path) -> JobContext:
    spec = JobSpec.model_validate_json((job_dir / "spec.json").read_text(encoding="utf-8"))
    pr = json.loads((job_dir / "probe.json").read_text(encoding="utf-8"))
    info = Probe(duration=pr["duration"], width=pr["width"], height=pr["height"], has_audio=pr["has_audio"])
    transcript = [
        TranscriptSegment(**t) for t in json.loads((job_dir / "transcript.json").read_text(encoding="utf-8"))
    ]
    frame_index = json.loads((job_dir / "frames.json").read_text(encoding="utf-8"))
    frames = [(f["t"], job_dir / "frames" / f["file"]) for f in frame_index]
    src = next((job_dir / "input").glob("source.*"))
    return JobContext(
        job_dir=job_dir,
        spec=spec,
        src_rel=f"input/{src.name}",
        info=info,
        transcript=transcript,
        speech=speech_spans(transcript),
        frames=frames,
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
    policy: PolicyResult = apply_policy(ctx.spec, plan, ctx.transcript, ctx.info.duration, set(tracks))

    voice_files: list[tuple[float, str]] = []
    if policy.voice_lines:
        provider = make_provider(settings.tts_provider, settings.tts_voice)
        for k, line in enumerate(policy.voice_lines):
            rel = f"voice/v{k}.mp3"
            provider.synthesize(line.text, job_dir / rel)
            voice_files.append((line.start, rel))

    # Không có tiếng gốc và không có lời đọc: video sẽ im lặng. Khi đó tự đặt nhạc nền từ kho có giấy phép.
    voiced = sum(v.end - v.start for v in policy.voice_lines)
    needs_bed = (not policy.keep_audio) and voiced < 0.7 * policy.output_seconds
    if needs_bed and not policy.plan.music.track and tracks:
        auto = sorted(tracks)[0]
        policy.plan = policy.plan.model_copy(
            update={"music": policy.plan.music.model_copy(update={"track": auto})}
        )
        policy.warnings.append(
            f"Ít tiếng (lời đọc dưới 70% thời lượng): tự đặt nhạc nền '{auto}' từ kho có giấy phép"
        )

    music_rel: str | None = None
    if policy.plan.music.track:
        track: Track = tracks[policy.plan.music.track]
        music_rel = f"music/{track.id}{track.file.suffix}"
        (job_dir / "music").mkdir(exist_ok=True)
        shutil.copy2(track.file, job_dir / music_rel)

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
    )
    output = render(ffmpeg, job_dir, job, settings.font_file)

    _write_json(job_dir / "plan.json", policy.plan.model_dump(mode="json"))
    # Điểm cắt theo kế hoạch trên timeline đầu ra; QA dùng để đếm nhịp cắt chính xác.
    _write_json(job_dir / "cuts.json", [round(p.out_offset, 3) for p in policy.pieces[1:]])
    _write_report(job_dir, ctx.spec, ctx.info.duration, policy, tracks)
    return RunResult(job_dir=job_dir, output=output, plan=policy.plan, warnings=policy.warnings)


def run_job(settings: Settings, spec: JobSpec, plan_override: EditPlan | None = None) -> RunResult:
    ctx = prepare(settings, spec)
    plan = plan_override if plan_override is not None else plan_with_model(settings, ctx)
    return render_plan(settings, ctx, plan)


def _write_report(
    job_dir: Path, spec: JobSpec, src_duration: float, policy: PolicyResult, tracks: dict
) -> None:
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
