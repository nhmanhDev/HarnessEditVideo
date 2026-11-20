"""Dòng lệnh: python -m edit_agent run|check ..."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import load_settings
from .music import load_tracks
from .pipeline import plan_from_file, run_job
from .spec import JobSpec, JobType


def _cmd_run(args: argparse.Namespace) -> int:
    settings = load_settings()
    spec = JobSpec(
        input=args.input,
        job_type=JobType(args.type),
        captions=args.captions,
        max_output_seconds=args.max_seconds,
        language=args.language,
        style_notes=args.style or "",
    )
    plan = plan_from_file(Path(args.plan)) if args.plan else None
    result = run_job(settings, spec, plan_override=plan)
    print(f"Xong: {result.output}")
    print(f"Báo cáo: {result.job_dir / 'report.md'}")
    for w in result.warnings:
        print(f"  cảnh báo: {w}")
    return 0


def _cmd_check(_args: argparse.Namespace) -> int:
    settings = load_settings()
    rows = [
        ("ffmpeg", settings.ffmpeg, _has_tool(settings.ffmpeg)),
        ("ffprobe", settings.ffprobe, _has_tool(settings.ffprobe)),
        ("font có dấu", str(settings.font_file or "không thấy"), settings.font_file is not None),
        (
            "ANTHROPIC_API_KEY",
            "có" if os.environ.get("ANTHROPIC_API_KEY") else "thiếu",
            bool(os.environ.get("ANTHROPIC_API_KEY")),
        ),
        (
            "OPENAI_API_KEY (TTS)",
            "có" if os.environ.get("OPENAI_API_KEY") else "thiếu",
            bool(os.environ.get("OPENAI_API_KEY")),
        ),
        (
            "nhạc có giấy phép",
            str(len(load_tracks(settings.music_dir))),
            len(load_tracks(settings.music_dir)) > 0,
        ),
    ]
    for name, value, ok in rows:
        print(f"{'OK  ' if ok else 'THIẾU'} {name}: {value}")
    return 0


def _has_tool(name: str) -> bool:
    from shutil import which

    return which(name) is not None


def main(argv: list[str] | None = None) -> int:
    # Console Windows mặc định không in được tiếng Việt; ép UTF-8 để đọc báo cáo đúng.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="edit-agent", description="Dựng video từ link Drive hoặc file cục bộ."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Chạy đầy đủ một job")
    run_p.add_argument("--input", required=True, help="Link Google Drive công khai hoặc đường dẫn file")
    run_p.add_argument("--type", required=True, choices=[t.value for t in JobType])
    run_p.add_argument("--captions", action="store_true", help="Bật phụ đề (chỉ loại có lời)")
    run_p.add_argument("--max-seconds", type=float, default=60.0)
    run_p.add_argument("--language", default=None, help="Mã ngôn ngữ nói, ví dụ vi")
    run_p.add_argument("--style", default=None, help="Ghi chú phong cách, ví dụ 'nhịp nhanh, chữ to'")
    run_p.add_argument("--plan", default=None, help="Dùng kế hoạch có sẵn (JSON), bỏ qua bước gọi Claude")
    run_p.set_defaults(func=_cmd_run)

    check_p = sub.add_parser("check", help="Kiểm tra công cụ, khóa và thư viện nhạc")
    check_p.set_defaults(func=_cmd_check)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
