"""Lập kế hoạch dựng bằng Claude: gửi khung hình, transcript và yêu cầu, nhận về JSON kế hoạch."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from .config import REPO_ROOT
from .policy import Span
from .spec import EditPlan, JobSpec
from .transcribe import TranscriptSegment

SYSTEM_PROMPT_PATH = REPO_ROOT / "templates" / "planner-system.md"


class PlannerError(RuntimeError):
    pass


def extract_json_object(text: str) -> dict:
    """Lấy object JSON đầu tiên trong câu trả lời, kể cả khi model bọc trong khối mã."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise PlannerError("Câu trả lời không có JSON")
    return json.loads(text[start : end + 1])


def _fmt_spans(spans: list[Span]) -> str:
    if not spans:
        return "không có lời nói"
    return ", ".join(f"{s.start:.1f}–{s.end:.1f}s" for s in spans)


def build_content(
    spec: JobSpec,
    src_duration: float,
    speech: list[Span],
    transcript: list[TranscriptSegment],
    frames: list[tuple[float, Path]],
    tracks: list[str],
) -> list[dict]:
    lines = [f"[{s.start:.1f}–{s.end:.1f}s] {s.text}" for s in transcript[:250]]
    info = {
        "loai": spec.job_type.value,
        "phu_de": spec.captions,
        "gioi_han_giay": spec.max_output_seconds,
        "kich_thuoc": f"{spec.width}x{spec.height}",
        "do_dai_nguon_giay": round(src_duration, 2),
        "ghi_chu_phong_cach": spec.style_notes,
        "nhac_co_giay_phep": tracks,
    }
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                "Thông tin đầu vào (JSON):\n"
                + json.dumps(info, ensure_ascii=False, indent=2)
                + f"\n\nKhoảng có lời gốc trong video nguồn: {_fmt_spans(speech)}"
                + "\n\nTranscript (thời gian theo video nguồn):\n"
                + ("\n".join(lines) if lines else "(không có lời)")
                + "\n\nKhung hình lấy đều, nhãn là thời điểm trong video nguồn:"
            ),
        }
    ]
    for t, path in frames:
        content.append({"type": "text", "text": f"t={t:.1f}s"})
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                },
            }
        )
    content.append(
        {"type": "text", "text": "Trả về JSON kế hoạch dựng theo đúng định dạng trong hướng dẫn hệ thống."}
    )
    return content


def _candidate_lines(candidates: list[dict] | None) -> list[str]:
    """Đoạn gợi ý do harness đo (nhiều chi tiết, khác nhau về hình). Model được ưu tiên chọn từ đây."""
    if not candidates:
        return []
    rows = ", ".join(f"{c['start']:.1f}–{c['end']:.1f}s" for c in candidates)
    return [
        "## Đoạn gợi ý (harness đo độ chi tiết và độ khác biệt hình; nên chọn đoạn từ đây)",
        rows,
        "Đây là gợi ý theo số đo, không thay cho việc nhìn ảnh lưới: bỏ đoạn nào sản phẩm chỉ hiện một nửa.",
        "",
    ]


def build_packet(
    spec: JobSpec,
    src_duration: float,
    speech: list[Span],
    transcript: list[TranscriptSegment],
    tracks: list[str],
    candidates: list[dict] | None = None,
) -> str:
    """Gói thông tin dạng văn bản (packet.md) để người hoặc agent khác lập plan.json mà không cần API.

    Cùng nội dung với lời gọi model; khung hình nằm trong frames/, danh sách ở frames.json.
    """
    system = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    info = {
        "loai": spec.job_type.value,
        "phu_de": spec.captions,
        "gioi_han_giay": spec.max_output_seconds,
        "kich_thuoc": f"{spec.width}x{spec.height}",
        "do_dai_nguon_giay": round(src_duration, 2),
        "ghi_chu_phong_cach": spec.style_notes,
        "nhac_co_giay_phep": tracks,
    }
    lines = [f"[{s.start:.1f}–{s.end:.1f}s] {s.text}" for s in transcript]
    return "\n".join(
        [
            "# Gói lập kế hoạch dựng",
            "",
            "Đọc hướng dẫn dưới đây, xem các khung hình trong thư mục frames/ (danh sách trong frames.json),",
            "rồi viết plan.json đúng định dạng. Chạy: edit-agent render --job <thư mục job> --planner manual",
            "",
            "## Thông tin đầu vào",
            "```json",
            json.dumps(info, ensure_ascii=False, indent=2),
            "```",
            "",
            f"Khoảng có lời gốc trong video nguồn: {_fmt_spans(speech)}",
            "",
            *_candidate_lines(candidates),
            "## Transcript (thời gian theo video nguồn)",
            "\n".join(lines) if lines else "(không có lời)",
            "",
            "## Hướng dẫn lập kế hoạch (cùng nội dung gửi cho model)",
            system,
        ]
    )


def plan_edit(
    client,
    model: str,
    spec: JobSpec,
    src_duration: float,
    speech: list[Span],
    transcript: list[TranscriptSegment],
    frames: list[tuple[float, Path]],
    tracks: list[str],
) -> EditPlan:
    system = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    content = build_content(spec, src_duration, speech, transcript, frames, tracks)
    messages = [{"role": "user", "content": content}]
    last_error: Exception | None = None
    for _attempt in range(2):
        resp = client.messages.create(model=model, max_tokens=4000, system=system, messages=messages)
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        try:
            return EditPlan.model_validate(extract_json_object(text))
        except (PlannerError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            # Gửi lại đúng lỗi để model sửa, chỉ thử thêm một lần.
            messages = messages + [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": (
                        f"Kế hoạch không hợp lệ: {exc}. Trả lại JSON đúng định dạng, không kèm chữ khác."
                    ),
                },
            ]
    raise PlannerError(f"Model không trả được kế hoạch hợp lệ: {last_error}")
