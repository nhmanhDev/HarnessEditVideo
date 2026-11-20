"""Agent tự làm đến khi đạt: model lập kế hoạch, harness dựng và đo QA, model xem lại, sửa, chọn bản tốt nhất.

Chỉ cần đổi backend (claude-cli, anthropic, command) là thay được model; phần còn lại giữ nguyên.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .config import REPO_ROOT, Settings
from .llm import Backend, LLMError
from .pipeline import JobContext, prepare, render_plan
from .planner import PlannerError, build_packet, extract_json_object
from .qa import Measure, judge, measure
from .sheets import make_sheet, make_source_sheets
from .spec import EditPlan, JobSpec, JobType

CRITIC_PROMPT_PATH = REPO_ROOT / "templates" / "critic-system.md"
_PLAN_TAIL = "\n\nTrả về DUY NHẤT một object JSON kế hoạch dựng đúng định dạng trên. Không kèm chữ nào khác."


@dataclass
class Round:
    index: int
    plan: EditPlan
    video: Path
    qa: Measure
    score: float | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def qa_ok(self) -> bool:
        return not self.qa.failures


@dataclass
class AgentResult:
    job_dir: Path
    best: Round
    rounds: list[Round]


def _ensure_font(ctx: JobContext, settings: Settings) -> None:
    dst = ctx.job_dir / "font.ttf"
    if not dst.exists() and settings.font_file:
        shutil.copy2(settings.font_file, dst)


def _json_with_retry(backend: Backend, prompt: str, images: list[str], cwd: Path, validate):
    """Gọi model, lấy JSON và kiểm; lỗi thì gửi lại đúng lỗi một lần."""
    last: Exception | None = None
    text = ""
    for attempt in range(2):
        full = (
            prompt
            if attempt == 0
            else (f"{prompt}\n\nLần trước trả về không hợp lệ ({last}). Trả lại JSON đúng định dạng.")
        )
        text = backend.complete(full, images, cwd)
        try:
            return validate(extract_json_object(text))
        except (PlannerError, ValueError, json.JSONDecodeError) as exc:
            last = exc
    raise PlannerError(f"Model không trả kế hoạch hợp lệ sau 2 lần: {last}")


def plan_with_backend(backend: Backend, ctx: JobContext, settings: Settings, track_ids: list[str]) -> EditPlan:
    _ensure_font(ctx, settings)
    sheets = make_source_sheets(settings.ffmpeg, ctx.job_dir, ctx.src_rel, ctx.info.duration)
    cand_file = ctx.job_dir / "candidates.json"
    candidates = json.loads(cand_file.read_text(encoding="utf-8")) if cand_file.exists() else None
    packet = build_packet(ctx.spec, ctx.info.duration, ctx.speech, ctx.transcript, track_ids, candidates, ctx.clips)
    prompt = (
        packet
        + "\n\nẢnh lưới khung hình của video nguồn (mỗi ô ghi thời điểm giây trong video nguồn) "
        + "ở danh sách ảnh bên dưới, theo thứ tự thời gian."
        + _PLAN_TAIL
    )
    return _json_with_retry(backend, prompt, sheets, ctx.job_dir, EditPlan.model_validate)


def _review_prompt(ctx: JobContext, plan: EditPlan, m: Measure, track_ids: list[str]) -> str:
    critic = CRITIC_PROMPT_PATH.read_text(encoding="utf-8")
    spec = ctx.spec
    info = {
        "loai": spec.job_type.value,
        "phu_de": spec.captions,
        "gioi_han_giay": spec.max_output_seconds,
        "do_dai_nguon_giay": round(ctx.info.duration, 2),
        "nhac_co_giay_phep": track_ids,
    }
    return "\n".join(
        [
            critic,
            "",
            "# Thông tin job",
            json.dumps(info, ensure_ascii=False, indent=2),
            "",
            "# Kế hoạch hiện tại",
            json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2),
            "",
            "# Số đo QA của video đầu ra",
            json.dumps(
                {"loi": m.failures, "canh_bao": m.warnings, "lufs": m.lufs_integrated, "cat": m.cuts},
                ensure_ascii=False,
            ),
            "",
            "Các ảnh đầu (sheet_source*): lưới khung hình video NGUỒN theo thứ tự thời gian. "
            "Ảnh cuối (sheet_out*): lưới khung hình video ĐẦU RA. Trả về JSON chấm điểm.",
        ]
    )


def review(backend: Backend, ctx: JobContext, plan: EditPlan, m: Measure, out_sheet: str, track_ids: list[str]):
    def validate(d: dict):
        score = float(d["score"])
        revised = d.get("plan")
        return (
            score,
            [str(i) for i in d.get("issues", [])],
            EditPlan.model_validate(revised) if revised else None,
        )

    return _json_with_retry(
        backend,
        _review_prompt(ctx, plan, m, track_ids),
        [p.name for p in sorted(ctx.job_dir.glob("sheet_source*.jpg"))] + [out_sheet],
        ctx.job_dir,
        validate,
    )


def run_agent(
    settings: Settings,
    spec: JobSpec,
    backend: Backend,
    track_ids: list[str],
    rounds: int = 2,
    target_score: float = 8.0,
    ctx: JobContext | None = None,
) -> AgentResult:
    # Có sẵn ctx (job đã chuẩn bị) thì dùng lại, không chuẩn bị lại từ đầu.
    ctx = ctx or prepare(settings, spec)
    plan = plan_with_backend(backend, ctx, settings, track_ids)
    done: list[Round] = []
    expect_audio = spec.job_type == JobType.SPEECH_CAPTION

    for i in range(rounds + 1):
        result = render_plan(settings, ctx, plan)
        m = judge(measure(settings, result.output), expect_audio=expect_audio)
        saved = ctx.job_dir / f"final_r{i}.mp4"
        shutil.copy2(result.output, saved)
        (ctx.job_dir / f"plan_r{i}.json").write_text(
            json.dumps(result.plan.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        rnd = Round(index=i, plan=result.plan, video=saved, qa=m)
        out_sheet = make_sheet(
            settings.ffmpeg, ctx.job_dir, "final.mp4", f"sheet_out_r{i}.jpg", m.duration, max_frames=30
        )
        try:
            score, issues, revised = review(backend, ctx, result.plan, m, out_sheet, track_ids)
        except (LLMError, PlannerError) as exc:
            rnd.issues = [f"không chấm được: {exc}"]
            done.append(rnd)
            break
        rnd.score, rnd.issues = score, issues
        done.append(rnd)
        if i == rounds or (score >= target_score and rnd.qa_ok) or revised is None:
            break
        plan = revised

    scored = [r for r in done if r.score is not None]
    pool = [r for r in scored if r.qa_ok] or scored or done
    best = max(pool, key=lambda r: (r.score or 0, -r.index))
    shutil.copy2(best.video, ctx.job_dir / "final_best.mp4")
    _write_report(ctx.job_dir, done, best)
    return AgentResult(job_dir=ctx.job_dir, best=best, rounds=done)


def _write_report(job_dir: Path, rounds: list[Round], best: Round) -> None:
    lines = ["# Báo cáo agent", "", f"Bản chọn: vòng {best.index} (điểm {best.score})", ""]
    for r in rounds:
        lines.append(f"## Vòng {r.index}: điểm {r.score}, QA {'đạt' if r.qa_ok else 'chưa đạt'}")
        lines.append(f"- {r.qa.duration}s, {r.qa.lufs_integrated} LUFS, {r.qa.cuts} lần cắt")
        lines += [f"- lỗi QA: {f}" for f in r.qa.failures]
        lines += [f"- nhận xét: {i}" for i in r.issues]
        lines.append("")
    (job_dir / "agent_report.md").write_text("\n".join(lines), encoding="utf-8")
