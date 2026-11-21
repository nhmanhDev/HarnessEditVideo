"""Kiểm các nâng cấp chất lượng: nền mờ, chuẩn âm lượng, fade nhạc, và bộ QA đánh giá."""

from edit_agent.policy import Piece
from edit_agent.qa import THRESHOLDS, Measure, judge
from edit_agent.render import RenderJob, build_filter_graph


def _job(**kw):
    base = dict(
        source="input/source.mp4",
        pieces=[Piece(0, 2, 0), Piece(4, 6, 2)],
        output_seconds=4,
        width=1440,
        height=2560,
        fps=30,
        keep_audio=False,
        output="final.mp4",
    )
    base.update(kw)
    return RenderJob(**base)


def test_blur_fit_keeps_full_frame_over_blurred_background():
    graph, _v, _a = build_filter_graph(_job(fit="blur"))
    assert "boxblur" in graph
    assert "overlay=(W-w)/2:(H-h)/2" in graph
    # Nền phóng to lấp khung, lớp trước vừa chiều rộng: không cắt mất hai bên.
    assert "scale=1440:-2" in graph


def test_crop_fit_keeps_the_old_full_bleed_chain():
    graph, _v, _a = build_filter_graph(_job(fit="crop"))
    assert "boxblur" not in graph
    assert "crop=1440:2560" in graph


def test_final_audio_is_loudness_normalised_to_target():
    graph, _v, audio = build_filter_graph(_job(keep_audio=True, music_file="music/a.mp3", loudness_lufs=-14.0))
    assert audio == "afinal"
    assert "loudnorm=I=-14.0:TP=-1.5:LRA=11" in graph


def test_loudness_normalisation_can_be_disabled():
    graph, _v, _a = build_filter_graph(_job(keep_audio=True, loudness_lufs=None))
    assert "loudnorm" not in graph


def test_music_has_fade_in_and_fade_out():
    graph, _v, _a = build_filter_graph(_job(music_file="music/a.mp3", music_fade_in_s=0.5, music_fade_out_s=1.5))
    assert "afade=t=in:st=0:d=0.50" in graph
    # Fade ra kết thúc tại (độ dài - 1,5 giây).
    assert "afade=t=out:st=2.500:d=1.50" in graph


def _good(**kw) -> Measure:
    base = dict(
        file="x.mp4",
        duration=20.0,
        width=1440,
        height=2560,
        has_audio=True,
        lufs_integrated=-14.2,
        lra=6.0,
        true_peak_dbfs=-1.2,
        silence_s=0.0,
        black_s=0.0,
        freeze_count=0,
        freeze_max_s=0.0,
        cuts=8,
        cuts_per_10s=4.0,
        shot_median_s=2.2,
        shot_max_s=2.4,
    )
    base.update(kw)
    return Measure(**base)


def test_qa_passes_a_good_reel():
    m = judge(_good(), expect_audio=True)
    assert m.failures == []
    assert all(m.checks.values())


def test_qa_fails_quiet_mix_and_clipping():
    quiet = judge(_good(lufs_integrated=-19.0), expect_audio=True)
    assert any("LUFS" in f for f in quiet.failures)
    clipped = judge(_good(true_peak_dbfs=0.3), expect_audio=True)
    assert any("dBTP" in f for f in clipped.failures)


def test_qa_fails_long_silence_and_black_frames():
    m = judge(_good(silence_s=10.9, black_s=2.0), expect_audio=True)
    assert any("im lặng" in f for f in m.failures)
    assert any("khung đen" in f for f in m.failures)


def test_qa_shot_rhythm_is_only_a_warning():
    m = judge(_good(shot_median_s=5.0, cuts=3), expect_audio=True)
    assert m.failures == []
    assert any("cảnh trung vị" in w for w in m.warnings)


def test_qa_rejects_landscape_output():
    m = judge(_good(width=1920, height=1080), expect_audio=True)
    assert any("không phải dọc" in f for f in m.failures)


def test_thresholds_match_reference_reels():
    # Ngưỡng phải nới đủ để 6 reel mẫu đạt (đo 2026-11-20).
    assert THRESHOLDS["true_peak_max"] >= -0.5
    assert THRESHOLDS["freeze_max_s"] >= 1.6
