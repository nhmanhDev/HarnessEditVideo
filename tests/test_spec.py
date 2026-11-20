import pytest
from pydantic import ValidationError

from edit_agent.intake import is_drive_link
from edit_agent.spec import EditPlan, JobSpec, JobType


def test_plan_requires_at_least_one_segment():
    with pytest.raises(ValidationError):
        EditPlan(segments=[])


def test_plan_rejects_unknown_text_position():
    with pytest.raises(ValidationError):
        EditPlan(
            segments=[{"src_start": 0, "src_end": 1}],
            texts=[{"text": "x", "start": 0, "end": 1, "position": "left"}],
        )


def test_job_type_values_match_cli_choices():
    assert JobType("text_music") is JobType.TEXT_MUSIC
    assert JobType("speech_music_caption") is JobType.SPEECH_CAPTION


def test_job_spec_defaults_to_vertical_reel():
    spec = JobSpec(input="x.mp4", job_type=JobType.TEXT_MUSIC)
    assert (spec.width, spec.height, spec.fps) == (1080, 1920, 30)


def test_drive_link_detection():
    assert is_drive_link("https://drive.google.com/file/d/abc/view?usp=sharing")
    assert not is_drive_link("clip.mp4")
