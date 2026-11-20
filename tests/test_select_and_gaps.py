from edit_agent.policy import uncovered_seconds
from edit_agent.select import pick_windows
from edit_agent.spec import VoiceLine


def test_uncovered_counts_tail_and_gaps():
    lines = [VoiceLine(text="a", start=0.1, end=3.0), VoiceLine(text="b", start=6.0, end=8.0)]
    # Phủ 2,9 + 2,0 = 4,9 giây trên 13,2 giây; khoảng không lời = 8,3 giây.
    assert round(uncovered_seconds(lines, 13.2), 2) == 8.3


def test_uncovered_is_zero_when_voice_covers_all():
    lines = [VoiceLine(text="a", start=0, end=5), VoiceLine(text="b", start=4.5, end=10)]
    assert uncovered_seconds(lines, 10.0) == 0.0


def test_pick_windows_prefers_high_detail_and_spreads_out():
    # Điểm thấp ở đầu, cao ở giữa và cuối.
    scores = [(i * 0.5, 1.0 if i < 10 else 9.0) for i in range(40)]
    wins = pick_windows(scores, 3, 2.0, 20.0, min_gap=0.5)
    assert len(wins) == 3
    assert all(w.start >= 5.0 for w in wins)
    assert all(wins[i].end + 0.5 <= wins[i + 1].start for i in range(len(wins) - 1))
