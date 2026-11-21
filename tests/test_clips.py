import shutil
import subprocess

import pytest

from edit_agent.clips import combine_clips, list_videos, split_at_boundaries
from edit_agent.media import probe
from edit_agent.planner import _clip_lines
from edit_agent.policy import apply_policy
from edit_agent.spec import EditPlan, JobSpec, JobType, Segment

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def test_split_cuts_segment_that_crosses_a_boundary():
    segs, notes = split_at_boundaries([(8.0, 12.0)], [10.0])
    assert segs == [(8.0, 10.0)]
    assert notes and "ranh giới" in notes[0]


def test_split_drops_tiny_remainder_and_keeps_clean_segments():
    segs, notes = split_at_boundaries([(9.7, 12.0), (1.0, 3.0)], [10.0])
    assert segs == [(1.0, 3.0)]
    assert len(notes) == 1


def test_policy_enforces_clip_boundaries():
    spec = JobSpec(input="x", job_type=JobType.TEXT_MUSIC)
    plan = EditPlan(segments=[Segment(src_start=8, src_end=12), Segment(src_start=15, src_end=17)])
    res = apply_policy(spec, plan, [], 30.0, set(), boundaries=[10.0])
    assert [(s.src_start, s.src_end) for s in res.plan.segments] == [(8.0, 10.0), (15.0, 17.0)]
    assert any("ranh giới" in w for w in res.warnings)


def test_clip_lines_only_appear_for_multiple_clips():
    assert _clip_lines([{"index": 0, "name": "a.mp4", "start": 0, "end": 5}]) == []
    lines = _clip_lines(
        [
            {"index": 0, "name": "a.mp4", "start": 0, "end": 5},
            {"index": 1, "name": "b.mp4", "start": 5, "end": 9},
        ]
    )
    assert any("clip 1 (b.mp4): 5.0–9.0s" in line for line in lines)
    assert any("KHÔNG chọn đoạn vượt qua ranh giới" in line for line in lines)


@pytest.mark.skipif(not HAS_FFMPEG, reason="cần ffmpeg và ffprobe trong PATH")
def test_combine_clips_joins_clips_with_and_without_audio(tmp_path):
    folder = tmp_path / "in"
    folder.mkdir()

    def make(name, seconds, with_audio):
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={seconds}:size=640x360:rate=25",
        ]
        if with_audio:
            cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(folder / name)]
        subprocess.run(cmd, check=True)

    make("2.mp4", 2, True)
    make("10.mp4", 3, False)
    clips = list_videos(folder)
    # Thứ tự tên tự nhiên: 2 trước 10.
    assert [c.name for c in clips] == ["2.mp4", "10.mp4"]

    out = tmp_path / "source.mp4"
    meta = combine_clips("ffmpeg", "ffprobe", clips, out, tmp_path / "work")
    info = probe("ffprobe", out)
    assert info.has_audio
    assert abs(info.duration - 5.0) < 0.3
    assert meta[0]["start"] == 0.0
    assert abs(meta[0]["end"] - 2.0) < 0.2
    assert abs(meta[1]["start"] - meta[0]["end"]) < 0.01
    assert [m["name"] for m in meta] == ["2.mp4", "10.mp4"]
