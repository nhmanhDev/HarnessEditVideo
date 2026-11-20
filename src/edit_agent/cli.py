"""Dòng lệnh: python -m edit_agent prepare | render | run | profile | check"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from shutil import which

from .config import load_settings
from .music import load_tracks
from .pipeline import (
    load_context,
    plan_from_file,
    plan_with_model,
    prepare,
    render_plan,
    run_job,
)
from .spec import JobSpec, JobType


def _spec_from_args(args: argparse.Namespace) -> JobSpec:
    return JobSpec(
        input=args.input,
        job_type=JobType(args.type),
        captions=args.captions,
        max_output_seconds=args.max_seconds,
        language=args.language,
        style_notes=args.style or "",
    )


def _print_result(result) -> None:
    print(f"Xong: {result.output}")
    print(f"Báo cáo: {result.job_dir / 'report.md'}")
    for w in result.warnings:
        print(f"  cảnh báo: {w}")


def _cmd_prepare(args: argparse.Namespace) -> int:
    settings = load_settings()
    ctx = prepare(settings, _spec_from_args(args))
    print(f"Job: {ctx.job_dir}")
    print(f"Gói lập kế hoạch: {ctx.job_dir / 'packet.md'}")
    print(f"Khung hình: {len(ctx.frames)} tấm trong {ctx.job_dir / 'frames'}")
    print("Viết plan.json rồi chạy: edit-agent render --job <thư mục job> --planner manual")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    settings = load_settings()
    job_dir = Path(args.job)
    ctx = load_context(job_dir)
    if args.planner == "manual":
        plan_path = job_dir / "plan.json"
        if args.plan:
            plan_path = Path(args.plan)
        if not plan_path.exists():
            raise FileNotFoundError(f"Chưa có kế hoạch: {plan_path}. Viết plan.json trước khi dựng.")
        plan = plan_from_file(plan_path)
    else:
        plan = plan_with_model(settings, ctx)
    _print_result(render_plan(settings, ctx, plan))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    settings = load_settings()
    plan = plan_from_file(Path(args.plan)) if args.plan else None
    _print_result(run_job(settings, _spec_from_args(args), plan_override=plan))
    return 0


def _cmd_agent(args: argparse.Namespace) -> int:
    from .agent import run_agent
    from .llm import make_backend

    settings = load_settings()
    spec = _spec_from_args(args)
    name = args.backend or settings.planner_backend
    client = None
    if name == "anthropic":
        import anthropic

        client = anthropic.Anthropic()
    backend = make_backend(
        name,
        claude_bin=settings.claude_bin,
        claude_model=settings.claude_model,
        command=settings.planner_cmd,
        anthropic_client=client,
        anthropic_model=settings.edit_model,
    )
    tracks = sorted(load_tracks(settings.music_dir))
    result = run_agent(settings, spec, backend, tracks, rounds=args.rounds)
    print(f"Job: {result.job_dir}")
    for r in result.rounds:
        status = "QA đạt" if r.qa_ok else "QA chưa đạt"
        print(f"  vòng {r.index}: điểm {r.score}, {status}, {r.qa.duration}s")
        for issue in r.issues:
            print(f"    - {issue}")
    print(f"Bản chọn: vòng {result.best.index} -> {result.job_dir / 'final_best.mp4'}")
    return 0


def _cmd_qa(args: argparse.Namespace) -> int:
    import json

    from .qa import judge, measure

    settings = load_settings()
    reports = []
    worst = 0
    for f in args.files:
        m = judge(measure(settings, Path(f)), expect_audio=not args.silent)
        reports.append(m.as_dict())
        status = "ĐẠT" if not m.failures else "CHƯA ĐẠT"
        worst = worst or (1 if m.failures else 0)
        print(f"{status}  {m.file}  {m.duration}s  {m.width}x{m.height}")
        print(f"    âm lượng {m.lufs_integrated} LUFS, đỉnh {m.true_peak_dbfs} dBTP, im lặng {m.silence_s}s")
        print(f"    cảnh: {m.cuts} lần cắt, trung vị {m.shot_median_s}s, dài nhất {m.shot_max_s}s")
        print(f"    khung đen {m.black_s}s, đứng hình tối đa {m.freeze_max_s}s")
        for msg in m.failures:
            print(f"    - LỖI: {msg}")
        for msg in m.warnings:
            print(f"    - cảnh báo: {msg}")
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Ghi báo cáo: {args.out}")
    return worst


def _cmd_profile(args: argparse.Namespace) -> int:
    from .profile import profile_videos

    settings = load_settings()
    out = Path(args.out)
    profile_videos([Path(v) for v in args.videos], out, settings)
    print(f"Đã ghi hồ sơ: {out}")
    return 0


def _cmd_check(_args: argparse.Namespace) -> int:
    settings = load_settings()
    tracks = load_tracks(settings.music_dir)
    rows = [
        ("ffmpeg", settings.ffmpeg, which(settings.ffmpeg) is not None),
        ("ffprobe", settings.ffprobe, which(settings.ffprobe) is not None),
        ("font có dấu", str(settings.font_file or "không thấy"), settings.font_file is not None),
        ("TTS", f"{settings.tts_provider} ({os.environ.get('TTS_BASE_URL', 'http://127.0.0.1:8891')})", True),
        (
            "ANTHROPIC_API_KEY (tùy chọn, chỉ cho --planner anthropic)",
            "có" if os.environ.get("ANTHROPIC_API_KEY") else "chưa có",
            bool(os.environ.get("ANTHROPIC_API_KEY")),
        ),
        ("nhạc có giấy phép", str(len(tracks)), len(tracks) > 0),
    ]
    for name, value, ok in rows:
        print(f"{'OK  ' if ok else 'THIẾU'} {name}: {value}")
    return 0


def _add_spec_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--input", required=True, help="Link Google Drive công khai hoặc đường dẫn file")
    p.add_argument("--type", required=True, choices=[t.value for t in JobType])
    p.add_argument("--captions", action="store_true", help="Bật phụ đề (chỉ loại có lời)")
    p.add_argument("--max-seconds", type=float, default=60.0)
    p.add_argument("--language", default=None, help="Mã ngôn ngữ nói, ví dụ vi")
    p.add_argument("--style", default=None, help="Ghi chú phong cách, ví dụ 'nhịp nhanh, chữ to'")


def main(argv: list[str] | None = None) -> int:
    # Console Windows mặc định không in được tiếng Việt; ép UTF-8 để đọc báo cáo đúng.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="edit-agent", description="Dựng video từ link Drive hoặc file cục bộ."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare", help="Bước 1: nhận video, nhận dạng lời, lấy khung hình, viết packet.md")
    _add_spec_args(prep)
    prep.set_defaults(func=_cmd_prepare)

    rend = sub.add_parser("render", help="Bước 2: đọc plan.json (hoặc lập bằng model), kiểm quy tắc, dựng")
    rend.add_argument("--job", required=True, help="Thư mục job do prepare tạo")
    rend.add_argument("--planner", choices=["manual", "anthropic"], default="manual")
    rend.add_argument("--plan", default=None, help="Đường dẫn plan.json khác (chỉ với --planner manual)")
    rend.set_defaults(func=_cmd_render)

    run_p = sub.add_parser("run", help="Chạy đầy đủ: prepare, lập bằng Claude, dựng")
    _add_spec_args(run_p)
    run_p.add_argument("--plan", default=None, help="Dùng kế hoạch có sẵn (JSON), bỏ qua Claude")
    run_p.set_defaults(func=_cmd_run)

    agent_p = sub.add_parser("agent", help="Làm trọn vẹn: model lập kế hoạch, dựng, đo QA, tự xem lại và sửa")
    _add_spec_args(agent_p)
    agent_p.add_argument("--backend", choices=["claude-cli", "anthropic", "command"], default=None)
    agent_p.add_argument("--rounds", type=int, default=2, help="Số vòng sửa tối đa sau lần dựng đầu")
    agent_p.set_defaults(func=_cmd_agent)

    qa_p = sub.add_parser("qa", help="Đo chất lượng video bằng số: âm lượng, khung đen, đứng hình, nhịp cắt")
    qa_p.add_argument("files", nargs="+")
    qa_p.add_argument("--out", default=None, help="Ghi báo cáo JSON")
    qa_p.add_argument("--silent", action="store_true", help="Video không có tiếng là đúng (loại không lời)")
    qa_p.set_defaults(func=_cmd_qa)

    prof = sub.add_parser("profile", help="Đo nhịp cắt và giọng của video mẫu, ghi hồ sơ JSON")
    prof.add_argument("videos", nargs="+", help="Các file video mẫu")
    prof.add_argument("--out", required=True, help="File JSON đầu ra")
    prof.set_defaults(func=_cmd_profile)

    check_p = sub.add_parser("check", help="Kiểm tra công cụ, khóa và thư viện nhạc")
    check_p.set_defaults(func=_cmd_check)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
