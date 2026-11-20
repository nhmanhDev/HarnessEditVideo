"""Luồng đầy đủ: nhận video, nhận dạng giọng nói, lập kế hoạch, kiểm quy tắc, tạo lời đọc, dựng, báo cáo."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings, require_tool
from .intake import fetch_source, new_job_dir
from .media import extract_audio_wav, extract_frames, probe
from .music import load_tracks
from .planner import plan_edit
from .policy import PolicyResult, apply_policy, speech_spans
from .render import RenderJob, render
from .spec import EditPlan, JobSpec
from .transcribe import TranscriptSegment, transcribe
from .tts import make_provider


@dataclass
class RunResult:
    job_dir: Path
    output: Path
    plan: EditPlan
    warnings: list[str] = field(default_factory=list)


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_client():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("Thiếu ANTHROPIC_API_KEY trong .env để lập kế hoạch dựng.")
    import anthropic

    return anthropic.Anthropic(api_key=key)


def run_job(settings: Settings, spec: JobSpec, plan_override: EditPlan | None = None) -> RunResult:
    ffmpeg = require_tool(settings.ffmpeg)
    ffprobe = require_tool(settings.ffprobe)

    job_dir = new_job_dir(settings, Path(spec.input).stem if not spec.input.startswith("http") else "drive")
    _write_json(job_dir / "spec.json", spec.model_dump(mode="json"))

    src = fetch_source(spec.input, job_dir)
    info = probe(ffprobe, src)
    rel_src = f"input/{src.name}"

    transcript: list[TranscriptSegment] = []
    if info.has_audio:
        wav = extract_audio_wav(ffmpeg, src, job_dir / "audio.wav")
        transcript = transcribe(wav, settings.whisper_model, spec.language)
    _write_json(job_dir / "transcript.json", [t.to_dict() for t in transcript])
    speech = speech_spans(transcript)

    tracks = load_tracks(settings.music_dir)

    if plan_override is not None:
        plan = plan_override
    else:
        frames = extract_frames(ffmpeg, src, job_dir / "frames", info.duration)
        client = _make_client()
        plan = plan_edit(
            client, settings.edit_model, spec, info.duration, speech, transcript, frames, sorted(tracks)
        )
    _write_json(job_dir / "plan.raw.json", plan.model_dump(mode="json"))

    policy: PolicyResult = apply_policy(spec, plan, transcript, info.duration, set(tracks))

    voice_files: list[tuple[float, str]] = []
    if policy.voice_lines:
        provider = make_provider(settings.tts_provider, settings.tts_voice)
        for k, line in enumerate(policy.voice_lines):
            rel = f"voice/v{k}.mp3"
            provider.synthesize(line.text, job_dir / rel)
            voice_files.append((line.start, rel))

    music_rel: str | None = None
    if policy.plan.music.track:
        track = tracks[policy.plan.music.track]
        music_rel = f"music/{track.id}{track.file.suffix}"
        (job_dir / "music").mkdir(exist_ok=True)
        shutil.copy2(track.file, job_dir / music_rel)

    job = RenderJob(
        source=rel_src,
        pieces=policy.pieces,
        output_seconds=policy.output_seconds,
        width=spec.width,
        height=spec.height,
        fps=spec.fps,
        keep_audio=policy.keep_audio,
        texts=policy.plan.texts,
        subtitles=policy.subtitles,
        voice_files=voice_files,
        music_file=music_rel,
        music_volume=policy.plan.music.volume,
        output="final.mp4",
    )
    output = render(ffmpeg, job_dir, job, settings.font_file)

    _write_json(job_dir / "plan.json", policy.plan.model_dump(mode="json"))
    _write_report(job_dir, spec, info.duration, policy, tracks)
    return RunResult(job_dir=job_dir, output=output, plan=policy.plan, warnings=policy.warnings)


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
