from edit_agent.profile import shot_lengths


def test_shot_lengths_from_cut_times():
    assert shot_lengths([2.0, 5.0], 8.0) == [2.0, 3.0, 3.0]


def test_shot_lengths_ignore_cuts_outside_video_and_tiny_shots():
    assert shot_lengths([0.01, 4.0, 4.02, 99.0], 6.0) == [3.99, 1.98]


def test_shot_lengths_empty_when_no_cuts():
    assert shot_lengths([], 5.0) == [5.0]
