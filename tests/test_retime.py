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


def test_recenter_moves_window_onto_the_product_and_keeps_length():
    from edit_agent.retime import recenter

    # Sản phẩm hiện ở giây 5–9 (mức 20), còn lại là rèm trống (mức 3).
    detail = [(i * 0.5, 20.0 if 5.0 <= i * 0.5 < 9.0 else 3.0) for i in range(30)]
    thresh = empty_threshold(detail)
    s, e = recenter(3.8, 6.0, detail, thresh, lo=0.0, hi=15.0)
    assert abs((e - s) - 2.2) < 1e-6
    assert s > 3.8  # đã dịch vào vùng có sản phẩm (dịch tối đa 1,2 giây)


def test_recenter_never_leaves_the_clip_bounds():
    from edit_agent.retime import recenter

    detail = [(i * 0.5, 20.0 if i * 0.5 >= 10.0 else 3.0) for i in range(30)]
    s, e = recenter(8.0, 10.2, detail, empty_threshold(detail), lo=7.0, hi=10.5)
    assert 7.0 <= s and e <= 10.5


def test_recenter_keeps_window_when_nothing_is_better():
    from edit_agent.retime import recenter

    detail = [(i * 0.5, 10.0) for i in range(30)]
    assert recenter(3.0, 5.2, detail, empty_threshold(detail), 0.0, 15.0) == (3.0, 5.2)


def test_recenter_prefers_a_settled_window_over_a_sliding_one():
    from edit_agent.retime import recenter

    # Sản phẩm hiện ở giây 4–10. Giây 4–6 đang trượt vào (chuyển động mạnh), từ giây 6 trở đi đứng yên.
    detail = [(i * 0.5, 20.0 if 4.0 <= i * 0.5 < 10.0 else 3.0) for i in range(30)]
    motion = [(i * 0.5, 15.0 if 4.0 <= i * 0.5 < 6.0 else 1.0) for i in range(30)]
    s, e = recenter(4.2, 6.4, detail, empty_threshold(detail), lo=0.0, hi=15.0, motion=motion)
    assert s > 4.2  # dời về phía lúc sản phẩm đã yên vị (dịch tối đa 1,2 giây)


def test_recenter_rejects_a_shift_that_jumps_to_a_different_item():
    from edit_agent.retime import recenter

    # Sản phẩm A hiện ở giây 3,5–4,5 (ngắn hơn cửa sổ), sản phẩm B ở giây 6–9. Cửa sổ ban đầu đặt ở A nhưng có khung trống ở cuối.
    detail = [(i * 0.5, 20.0 if (3.5 <= i * 0.5 < 4.5 or 6.0 <= i * 0.5 < 9.0) else 3.0) for i in range(30)]
    thresh = empty_threshold(detail)

    def drift(a, b, c, d):
        # Cửa sổ nằm trong vùng B (từ giây 6) coi như món khác hẳn.
        return 30.0 if c >= 5.6 else 1.0

    free = recenter(3.4, 5.6, detail, thresh, 0.0, 15.0, max_shift=3.0)
    guarded = recenter(3.4, 5.6, detail, thresh, 0.0, 15.0, max_shift=3.0, drift=drift)
    assert free[0] >= 5.6  # không có ràng buộc thì nhảy sang món B
    assert guarded[0] < 5.6  # có ràng buộc thì ở lại món A
