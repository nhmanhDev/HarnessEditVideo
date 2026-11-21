"""Chọn lại từng đoạn cắt bằng ảnh dày: model xem khung hình mỗi 0,3 giây quanh đoạn rồi chỉ ra cửa sổ sạch nhất.

Ảnh lưới của cả video nguồn chỉ có một khung mỗi ~1,7 giây nên model không thấy lúc món vào hoặc ra khỏi khung.
Bước này cho model nhìn đủ dày; độ dài đoạn giữ nguyên để chữ và lời đọc vẫn khớp thời gian.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .config import Settings
from .llm import Backend, LLMError
from .pipeline import JobContext
from .planner import PlannerError, extract_json_object
from .sheets import make_sheet
from .spec import EditPlan, Segment

STEP = 0.3
MARGIN = 1.5

REFINE_PROMPT = """Bạn chọn cửa sổ thời gian đẹp nhất cho từng đoạn cắt của một reel bán hàng.
Mỗi ảnh lưới dưới đây là các khung hình của video nguồn, cách nhau 0,3 giây, mỗi ô ghi thời điểm giây trong video nguồn.
Với mỗi đoạn, chọn `src_start` sao cho toàn bộ cửa sổ [src_start, src_start + độ dài] thoả CẢ BỐN điều kiện:
1. Sản phẩm (áo, quần, váy, biển hiệu) nằm TRỌN trong khung, không bị cắt ở mép, không có rèm trống.
2. Sản phẩm đứng yên hoặc chỉ lắc nhẹ: không mờ do đang vào, đang ra hoặc bị tay kéo đi.
3. Không có vật lạ che (xe máy, người đi ngang) và không có khung chuyển cảnh.
4. Món trong cửa sổ đúng là món đang được nhắc trong `mo_ta` của đoạn (nếu có).
Ưu tiên cửa sổ mà sản phẩm ở giữa khung. Chỉ chọn thời điểm có trong ảnh lưới. Độ dài cửa sổ giữ NGUYÊN theo `do_dai`.
Nếu không có cửa sổ nào hoàn hảo, chọn cửa sổ ít lỗi nhất.
Đồng thời chọn `vi_tri_chu` cho đoạn: "top" hoặc "bottom", là nửa khung có nền trống để chữ KHÔNG đè lên sản phẩm
hay chữ in sẵn (biển hiệu, banner, chữ trên áo); nếu cả hai nửa đều có chữ in sẵn thì chọn nửa ít chữ hơn.
Trả về DUY NHẤT một JSON, đủ mọi đoạn, đúng thứ tự `i`:
{"segments":[{"i":0,"src_start":12.3,"vi_tri_chu":"bottom","ghi_chu":"lý do ngắn"}, ...]}"""


def _clip_bounds(ctx: JobContext, t: float) -> tuple[float, float]:
    for c in ctx.clips:
        if c["start"] - 1e-6 <= t < c["end"] + 1e-6:
            return float(c["start"]), float(c["end"])
    return 0.0, float(ctx.info.duration)


def _describe(plan: EditPlan, i: int) -> str:
    """Chữ nào đang gắn với đoạn thứ i theo timeline lý tưởng (độ dài các đoạn cộng dồn)."""
    t0 = sum(s.src_end - s.src_start for s in plan.segments[:i])
    t1 = t0 + (plan.segments[i].src_end - plan.segments[i].src_start)
    names = [t.text for t in plan.texts if t.start < t1 - 0.2 and t.end > t0 + 0.2]
    return "; ".join(names)


def refine_segments(
    backend: Backend, ctx: JobContext, settings: Settings, plan: EditPlan, place_texts: bool = True
) -> EditPlan:
    """Trả kế hoạch mới với src_start từng đoạn được chọn lại; lỗi thì giữ nguyên kế hoạch.

    place_texts=False: giữ nguyên vị trí chữ (kế hoạch đã được critic sửa, không ghi đè quyết định của nó).
    """
    rows: list[dict] = []
    sheets: list[str] = []
    bounds: list[tuple[float, float]] = []
    for i, seg in enumerate(plan.segments):
        length = seg.src_end - seg.src_start
        lo, hi = _clip_bounds(ctx, (seg.src_start + seg.src_end) / 2)
        bounds.append((lo, hi))
        w0, w1 = max(lo, seg.src_start - MARGIN), min(hi, seg.src_end + MARGIN)
        out = f"refine_{i}.jpg"
        make_sheet(
            settings.ffmpeg,
            ctx.job_dir,
            ctx.src_rel,
            out,
            w1 - w0,
            max_frames=40,
            tile_w=200,
            cols=6,
            start=w0,
            min_interval=STEP,
        )
        sheets.append(out)
        rows.append(
            {
                "i": i,
                "anh": out,
                "hien_tai": [round(seg.src_start, 2), round(seg.src_end, 2)],
                "do_dai": round(length, 2),
                "pham_vi_cho_phep": [round(w0, 2), round(w1, 2)],
                "mo_ta": _describe(plan, i),
            }
        )
    prompt = REFINE_PROMPT + "\n\nDanh sách đoạn (tên file ảnh nằm trong cột anh, theo đúng thứ tự):\n"
    prompt += json.dumps(rows, ensure_ascii=False, indent=2)
    try:
        text = backend.complete(prompt, sheets, ctx.job_dir)
        data = extract_json_object(text)["segments"]
        picked = {int(d["i"]): float(d["src_start"]) for d in data}
        places = {int(d["i"]): d.get("vi_tri_chu") for d in data if d.get("vi_tri_chu") in ("top", "bottom")}
    except (LLMError, PlannerError, KeyError, ValueError, TypeError) as exc:
        print(f"Cảnh báo: không chọn lại được đoạn ({exc}); giữ kế hoạch cũ", file=sys.stderr)
        return plan
    new: list[Segment] = []
    for i, seg in enumerate(plan.segments):
        length = seg.src_end - seg.src_start
        lo, hi = bounds[i]
        start = picked.get(i, seg.src_start)
        start = min(max(start, lo, rows[i]["pham_vi_cho_phep"][0]), min(hi, rows[i]["pham_vi_cho_phep"][1]) - length)
        new.append(Segment(src_start=round(start, 3), src_end=round(start + length, 3)))
    texts = _place_texts(plan, places) if place_texts else plan.texts
    return plan.model_copy(update={"segments": new, "texts": texts})


def _place_texts(plan: EditPlan, places: dict[int, str]) -> list:
    """Đặt lại vị trí chữ theo nửa khung model chọn cho đoạn chứa chữ đó (theo timeline lý tưởng)."""
    edges, t = [], 0.0
    for s in plan.segments:
        edges.append((t, t + s.src_end - s.src_start))
        t = edges[-1][1]
    out = []
    for text in plan.texts:
        mid = (text.start + text.end) / 2
        idx = next((i for i, (a, b) in enumerate(edges) if a <= mid < b), None)
        place = places.get(idx) if idx is not None else None
        out.append(text.model_copy(update={"position": place}) if place else text)
    return out


def save_plan(job_dir: Path, name: str, plan: EditPlan) -> None:
    (job_dir / name).write_text(
        json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
    )
