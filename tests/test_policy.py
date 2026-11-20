import pytest

from edit_agent.policy import Span, apply_policy, build_pieces, has_speech, map_span, speech_spans
from edit_agent.spec import EditPlan, JobSpec, JobType, Music, Segment, TextOverlay, VoiceLine
from edit_agent.transcribe import TranscriptSegment


def _spec(job_type=JobType.TEXT_MUSIC, captions=False, max_seconds=60.0):
    return JobSpec(input="x.mp4", job_type=job_type, captions=captions, max_output_seconds=max_seconds)


def _plan(**kw):
    base = dict(segments=[Segment(src_start=0, src_end=10)])
    base.update(kw)
    return EditPlan(**base)


def _tr(start, end, text="xin chào", prob=0.05):
    return TranscriptSegment(start=start, end=end, text=text, no_speech_prob=prob)


def test_speech_spans_merges_close_segments_and_skips_noise():
    tr = [_tr(1.0, 2.0), _tr(2.1, 3.0), _tr(6.0, 7.0, prob=0.9)]
    spans = speech_spans(tr)
    assert spans == [Span(1.0, 3.0)]
    assert has_speech(spans, min_total_seconds=1.5)
    assert not has_speech([Span(0, 0.5)])


def test_build_pieces_maps_output_timeline():
    pieces, total = build_pieces([Segment(src_start=2, src_end=4), Segment(src_start=10, src_end=13)], 20)
    assert total == 5
    assert pieces[1].out_offset == 2
    assert map_span(Span(11, 12), pieces) == [Span(3, 4)]
    assert map_span(Span(5, 9), pieces) == []


def test_build_pieces_rejects_segment_outside_source():
    with pytest.raises(ValueError):
        build_pieces([Segment(src_start=30, src_end=31)], 20)


def test_text_music_mutes_source_and_drops_voice_lines():
    plan = _plan(voice_lines=[VoiceLine(text="a", start=1, end=2)])
    res = apply_policy(_spec(JobType.TEXT_MUSIC), plan, [_tr(1, 3)], 10, set())
    assert res.keep_audio is False
    assert res.voice_lines == []
    assert any("không lời" in w for w in res.warnings)


def test_speech_source_keeps_voice_and_blocks_overlapping_tts():
    tr = [_tr(1.0, 4.0)]
    plan = _plan(
        voice_lines=[
            VoiceLine(text="trùng", start=2, end=3),
            VoiceLine(text="ok", start=5, end=6),
        ]
    )
    res = apply_policy(_spec(JobType.SPEECH_CAPTION), plan, tr, 10, set())
    assert res.keep_audio is True
    assert [v.text for v in res.voice_lines] == ["ok"]
    assert any("trùng lời gốc" in w for w in res.warnings)


def test_silent_source_allows_voice_lines_and_mutes_original():
    tr = [_tr(1.0, 2.0, prob=0.95)]
    plan = _plan(voice_lines=[VoiceLine(text="đọc", start=1, end=3)])
    res = apply_policy(_spec(JobType.SPEECH_CAPTION), plan, tr, 10, set())
    assert res.keep_audio is False
    assert [v.text for v in res.voice_lines] == ["đọc"]
    assert any("không có lời nói" in w for w in res.warnings)


def test_voice_line_with_caption_false_is_spoken_but_not_subtitled():
    plan = _plan(
        voice_lines=[
            VoiceLine(text="áo đỏ", start=0, end=2),
            VoiceLine(text="giảm năm mươi phần trăm", start=3, end=5, caption=False),
        ]
    )
    res = apply_policy(_spec(JobType.SPEECH_CAPTION, captions=True), plan, [], 10, set())
    assert [v.text for v in res.voice_lines] == ["áo đỏ", "giảm năm mươi phần trăm"]
    assert [s.text for s in res.subtitles] == ["áo đỏ"]


def test_captions_come_from_transcript_on_output_timeline():
    tr = [_tr(3.0, 4.0, "câu một"), _tr(8.0, 9.0, "câu hai")]
    plan = _plan(segments=[Segment(src_start=2, src_end=5), Segment(src_start=7, src_end=10)])
    res = apply_policy(_spec(JobType.SPEECH_CAPTION, captions=True), plan, tr, 10, set())
    texts = [(s.start, s.end, s.text) for s in res.subtitles]
    assert texts == [(1.0, 2.0, "câu một"), (4.0, 5.0, "câu hai")]


def test_unknown_music_track_is_dropped_with_warning():
    plan = _plan(music=Music(track="khong-co", volume=0.3))
    res = apply_policy(_spec(), plan, [], 10, {"chill-01"})
    assert res.plan.music.track is None
    assert any("giấy phép" in w for w in res.warnings)


def test_text_after_end_is_dropped_and_end_clamped():
    plan = _plan(
        texts=[
            TextOverlay(text="sớm", start=0, end=99),
            TextOverlay(text="muộn", start=50, end=60),
        ]
    )
    res = apply_policy(_spec(), plan, [], 10, set())
    assert [t.text for t in res.plan.texts] == ["sớm"]
    assert res.plan.texts[0].end == 10


def test_output_longer_than_limit_is_rejected():
    plan = _plan(segments=[Segment(src_start=0, src_end=10)])
    with pytest.raises(ValueError):
        apply_policy(_spec(max_seconds=5), plan, [], 10, set())
