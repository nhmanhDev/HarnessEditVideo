from edit_agent.policy import apply_policy
from edit_agent.retime import Seg, empty_threshold, remap_time, snap, split_indexed, trim_empty_edges
from edit_agent.spec import EditPlan, JobSpec, JobType, Segment, TextOverlay

DETAIL = [(i * 0.5, 10.0) for i in range(40)]  # 20 giây, chi tiết đều 10


def _with_empty(*empty_ranges):
    out = []
    for t, d in DETAIL:
        out.append((t, 1.0 if any(a <= t < b for a, b in empty_ranges) else d))
    return out


def test_empty_threshold_is_below_normal_detail():
    assert 0 < empty_threshold(DETAIL) < 10.0


def test_trim_removes_empty_tail_but_keeps_minimum_length():
    detail = _with_empty((4.0, 6.0))  # khung trống từ giây 4 đến 6
    thresh = empty_threshold(detail)
    s, e = trim_empty_edges(2.0, 6.0, detail, thresh)
    assert s == 2.0 and e < 6.0
    assert e - s >= 1.2
    # Khung đầy đủ thì giữ nguyên.
    assert trim_empty_edges(8.0, 10.0, detail, thresh) == (8.0, 10.0)


def test_split_indexed_keeps_original_indices():
    segs, _notes = split_indexed([(0, 1.0, 3.0), (1, 8.0, 12.0), (2, 9.8, 10.2)], [10.0])
    assert [(s.orig, s.start, s.end) for s in segs] == [(0, 1.0, 3.0), (1, 8.0, 10.0)]


def test_remap_shifts_time_after_a_shortened_piece():
    planned = [(0, 2.0), (1, 2.0), (2, 2.0)]
    actual = [Seg(0, 0.0, 2.0), Seg(1, 5.0, 6.0), Seg(2, 9.0, 11.0)]  # đoạn 1 chỉ còn 1 giây
    out = 5.0
    # Chữ ở giây 4,5 (trong đoạn kế hoạch 2) phải dịch sớm 1 giây.
    assert remap_time(4.5, planned, actual, out) == 3.5
    assert remap_time(1.0, planned, actual, out) == 1.0


def test_remap_moves_time_of_dropped_piece_to_next_piece():
    planned = [(0, 2.0), (1, 2.0), (2, 2.0)]
    actual = [Seg(0, 0.0, 2.0), Seg(2, 9.0, 11.0)]  # đoạn 1 bị bỏ
    assert remap_time(2.5, planned, actual, 4.0) == 2.0


def test_snap_to_nearest_cut_within_tolerance_only():
    assert snap(2.3, [0.0, 2.2, 4.4], 0.6) == 2.2
    assert snap(3.2, [0.0, 2.2, 4.4], 0.6) == 3.2


def test_policy_realigns_text_when_a_segment_is_shortened_by_a_clip_boundary():
    spec = JobSpec(input="x", job_type=JobType.TEXT_MUSIC)
    plan = EditPlan(
        segments=[Segment(src_start=1, src_end=3), Segment(src_start=8, src_end=12), Segment(src_start=20, src_end=22)],
        texts=[TextOverlay(text="Món ba", start=6.0, end=8.0, position="bottom")],
    )
    res = apply_policy(spec, plan, [], 30.0, set(), boundaries=[10.0])
    # Đoạn 2 chỉ còn 2 giây (8–10) thay vì 4: chữ của đoạn ba (kế hoạch 6–8) dịch về 4–6 trên timeline thật.
    assert [(round(t.start, 1), round(t.end, 1)) for t in res.plan.texts] == [(4.0, 6.0)]
    assert res.output_seconds == 6.0
