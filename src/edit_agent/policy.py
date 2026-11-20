"""Quy tắc giọng nói và ánh xạ thời gian. Model đề xuất, lớp này quyết định cái gì được phép dựng.

Nguyên tắc chính:
- Không bao giờ thêm lời đọc (TTS) đè lên lời gốc đang có trong video.
- Không tạo lời gốc từ một đoạn không có tiếng nói.
- Loại 1 (không lời) luôn tắt tiếng gốc và không có lời đọc.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field

import numpy as np

from .retime import Seg, empty_threshold, recenter, remap_time, snap, split_indexed, trim_empty_edges
from .spec import EditPlan, JobSpec, JobType, Music, Segment, TextOverlay, VoiceLine
from .transcribe import TranscriptSegment


@dataclass(frozen=True)
class Span:
    start: float
    end: float


@dataclass(frozen=True)
class Piece:
    """Một đoạn cắt đã kiểm tra: thời điểm nguồn và vị trí trên timeline đầu ra."""

    src_start: float
    src_end: float
    out_offset: float


@dataclass(frozen=True)
class Subtitle:
    start: float
    end: float
    text: str


@dataclass
class PolicyResult:
    plan: EditPlan
    pieces: list[Piece]
    output_seconds: float
    keep_audio: bool
    voice_lines: list[VoiceLine]
    subtitles: list[Subtitle]
    warnings: list[str] = field(default_factory=list)

    @property
    def speech_in_output(self) -> bool:
        return self.keep_audio or bool(self.voice_lines)


def speech_spans(transcript: list[TranscriptSegment], max_no_speech: float = 0.5, gap: float = 0.3) -> list[Span]:
    """Các khoảng có tiếng nói ở video nguồn, đã gộp các đoạn liền nhau."""
    raw = sorted((s.start, s.end) for s in transcript if s.no_speech_prob < max_no_speech and s.end > s.start)
    merged: list[Span] = []
    for start, end in raw:
        if merged and start - merged[-1].end <= gap:
            merged[-1] = Span(merged[-1].start, max(merged[-1].end, end))
        else:
            merged.append(Span(start, end))
    return merged


def has_speech(spans: list[Span], min_total_seconds: float = 1.5) -> bool:
    return sum(s.end - s.start for s in spans) >= min_total_seconds


def build_pieces(segments: list[Segment], src_duration: float) -> tuple[list[Piece], float]:
    pieces: list[Piece] = []
    offset = 0.0
    for seg in segments:
        end = min(seg.src_end, src_duration)
        if end <= seg.src_start:
            raise ValueError(
                f"Đoạn cắt không hợp lệ: {seg.src_start:.2f}–{seg.src_end:.2f}s, video dài {src_duration:.2f}s"
            )
        pieces.append(Piece(seg.src_start, end, offset))
        offset += end - seg.src_start
    return pieces, offset


def map_span(span: Span, pieces: list[Piece]) -> list[Span]:
    """Đổi khoảng thời gian nguồn sang timeline đầu ra; phần nằm ngoài các đoạn giữ lại bị bỏ."""
    out: list[Span] = []
    for p in pieces:
        a, b = max(span.start, p.src_start), min(span.end, p.src_end)
        if b > a:
            out.append(Span(p.out_offset + (a - p.src_start), p.out_offset + (b - p.src_start)))
    return out


def _overlaps(a: Span, b: Span) -> bool:
    return a.start < b.end and b.start < a.end


def uncovered_seconds(voice_lines: list[VoiceLine], output_seconds: float) -> float:
    """Tổng thời gian trên timeline đầu ra không có lời đọc nào (các lời đọc có thể chồng lên nhau)."""
    spans = sorted((v.start, min(v.end, output_seconds)) for v in voice_lines if v.start < output_seconds)
    covered = 0.0
    cur_s, cur_e = None, None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                covered += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        covered += cur_e - cur_s
    return max(0.0, output_seconds - covered)


def _make_drift(detail: list[tuple[float, float]], sigs):
    """Hàm đo độ lệch hình giữa hai cửa sổ thời gian, từ chữ ký hình theo từng mẫu. None nếu thiếu chữ ký."""
    if sigs is None or not len(detail):
        return None
    times = [t for t, _ in detail]

    def window(a: float, b: float):
        i0, i1 = bisect.bisect_left(times, a), bisect.bisect_right(times, b)
        return sigs[i0:i1].mean(axis=0) if i1 > i0 else None

    def drift(a: float, b: float, c: float, d: float) -> float:
        wa, wc = window(a, b), window(c, d)
        return 0.0 if wa is None or wc is None else float(np.abs(wa - wc).mean())

    return drift


def apply_policy(
    spec: JobSpec,
    plan: EditPlan,
    transcript: list[TranscriptSegment],
    src_duration: float,
    known_tracks: set[str],
    boundaries: list[float] | None = None,
    detail: list[tuple[float, float]] | None = None,
    motion: list[tuple[float, float]] | None = None,
    sigs=None,
) -> PolicyResult:
    warnings: list[str] = []
    planned: list[tuple[int, float]] = []
    items: list[tuple[int, float, float]] = []
    for i, s in enumerate(plan.segments):
        end = min(s.src_end, src_duration)
        if end <= s.src_start:
            raise ValueError(
                f"Đoạn cắt không hợp lệ: {s.src_start:.2f}–{s.src_end:.2f}s, video dài {src_duration:.2f}s"
            )
        planned.append((i, end - s.src_start))
        items.append((i, s.src_start, end))

    if detail:
        # Cắt rìa khung trống (rèm, tay đang kéo đồ đi) ở đầu và cuối mỗi đoạn.
        thresh = empty_threshold(detail)
        clip_edges = [0.0, *sorted(boundaries or []), src_duration]
        drift = _make_drift(detail, sigs)
        trimmed = []
        for i, st, en in items:
            # Trước hết dịch cửa sổ trong cùng clip về chỗ sản phẩm hiện rõ (giữ nguyên độ dài đoạn).
            lo = max(e for e in clip_edges if e <= st + 1e-6)
            hi = min(e for e in clip_edges if e >= en - 1e-6)
            ms, me = recenter(st, en, detail, thresh, lo, hi, max_shift=2.5, motion=motion, drift=drift)
            if (ms, me) != (st, en):
                warnings.append(f"Dịch đoạn {st:.1f}–{en:.1f}s sang {ms:.1f}–{me:.1f}s để sản phẩm hiện rõ")
            # Còn rìa trống thì cắt bớt.
            ns, ne = trim_empty_edges(ms, me, detail, thresh, min_len=1.6)
            if (ns, ne) != (ms, me):
                warnings.append(f"Cắt rìa trống đoạn {ms:.1f}–{me:.1f}s còn {ns:.1f}–{ne:.1f}s")
            trimmed.append((i, ns, ne))
        items = trimmed

    if boundaries:
        # Nguồn gồm nhiều clip nối liền: đoạn cắt không được vượt qua ranh giới clip.
        actual, notes = split_indexed(items, boundaries)
        warnings += notes
        if not actual:
            raise ValueError("Mọi đoạn cắt đều vượt ranh giới clip")
    else:
        actual = [Seg(i, st, en) for i, st, en in items]
    segments = [Segment(src_start=s.start, src_end=s.end) for s in actual]
    pieces, out_seconds = build_pieces(segments, src_duration)
    if out_seconds > spec.max_output_seconds:
        raise ValueError(f"Video đầu ra {out_seconds:.1f}s dài hơn giới hạn {spec.max_output_seconds:.0f}s")

    def remap(t: float) -> float:
        return min(remap_time(t, planned, actual, out_seconds), out_seconds)

    # Thời điểm chữ trong kế hoạch tính theo timeline lý tưởng; dịch theo các đoạn đã rút ngắn rồi bám điểm cắt.
    cut_starts = [p.out_offset for p in pieces]
    cut_ends = [p.out_offset + (p.src_end - p.src_start) for p in pieces]
    texts: list[TextOverlay] = []
    for t in plan.texts:
        start, end = remap(t.start), remap(t.end)
        if start >= out_seconds - 0.3:
            warnings.append(f"Bỏ chữ '{t.text[:30]}': bắt đầu sau khi video kết thúc")
            continue
        start, end = snap(start, cut_starts, 0.6), snap(end, cut_ends, 0.6)
        if end - start < 1.0:
            end = min(out_seconds, start + 1.5)
        texts.append(t.model_copy(update={"start": start, "end": min(end, out_seconds)}))
    plan = plan.model_copy(
        update={
            "voice_lines": [
                line.model_copy(update={"start": remap(line.start), "end": remap(line.end)})
                for line in plan.voice_lines
            ]
        }
    )

    music = plan.music
    if music.track and music.track not in known_tracks:
        warnings.append(f"Bỏ nhạc '{music.track}': không có trong manifest nhạc có ghi giấy phép")
        music = Music(track=None, volume=music.volume)

    src_spans = speech_spans(transcript)
    source_has_voice = has_speech(src_spans)
    out_speech = [m for s in src_spans for m in map_span(s, pieces)]

    subtitles: list[Subtitle] = []
    voice_lines: list[VoiceLine] = []
    keep_audio = False

    if spec.job_type == JobType.TEXT_MUSIC:
        if plan.voice_lines:
            warnings.append("Loại không lời: bỏ toàn bộ lời đọc trong kế hoạch")
        if spec.captions:
            warnings.append("Loại không lời: không có phụ đề, bỏ qua tuỳ chọn phụ đề")
    else:
        # Loại có lời: giữ tiếng gốc nếu thật sự có lời, còn lại tắt để tránh tiếng ồn không có ý nghĩa.
        keep_audio = source_has_voice
        if not source_has_voice:
            warnings.append("Video nguồn không có lời nói: tắt tiếng gốc, chỉ dùng nhạc và lời đọc nếu có")

        accepted: list[Span] = []
        for line in plan.voice_lines:
            if line.start >= out_seconds:
                warnings.append(f"Bỏ lời đọc '{line.text[:30]}': nằm ngoài video")
                continue
            window = Span(line.start, min(line.end, out_seconds))
            if keep_audio and any(_overlaps(window, s) for s in out_speech):
                warnings.append(f"Bỏ lời đọc '{line.text[:30]}': trùng lời gốc đang phát")
                continue
            if any(_overlaps(window, a) for a in accepted):
                warnings.append(f"Bỏ lời đọc '{line.text[:30]}': trùng lời đọc khác")
                continue
            accepted.append(window)
            voice_lines.append(line.model_copy(update={"end": window.end}))

        if spec.captions:
            for seg in transcript:
                if seg.no_speech_prob >= 0.5 or not keep_audio:
                    continue
                for mapped in map_span(Span(seg.start, seg.end), pieces):
                    subtitles.append(Subtitle(mapped.start, mapped.end, seg.text))
            for line in voice_lines:
                subtitles.append(Subtitle(line.start, line.end, line.text))
            subtitles.sort(key=lambda s: s.start)

    final_plan = plan.model_copy(
        update={"segments": segments, "texts": texts, "voice_lines": voice_lines, "music": music}
    )
    return PolicyResult(
        plan=final_plan,
        pieces=pieces,
        output_seconds=out_seconds,
        keep_audio=keep_audio,
        voice_lines=voice_lines,
        subtitles=subtitles,
        warnings=warnings,
    )
