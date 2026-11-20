import shutil
import subprocess

import pytest

from edit_agent.config import load_settings
from edit_agent.media import probe
from edit_agent.policy import Piece, Subtitle
from edit_agent.render import RenderJob, build_filter_graph, render
from edit_agent.spec import TextOverlay

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _job(**kw):
    base = dict(
        source="input/source.mp4",
        pieces=[Piece(0, 2, 0), Piece(4, 6, 2)],
        output_seconds=4,
        width=1080,
        height=1920,
        fps=30,
        keep_audio=False,
        output="final.mp4",
    )
    base.update(kw)
    return RenderJob(**base)


def test_graph_concats_pieces_and_uses_relative_paths_only():
    job = _job(
        texts=[TextOverlay(text="Chào", start=0, end=2, position="top")],
        font_file="font.ttf",
        music_file="music/a.mp3",
        music_volume=0.3,
    )
    graph, video, audio = build_filter_graph(job)
    assert "concat=n=2:v=1:a=0[vc]" in graph
    assert "drawtext=fontfile=font.ttf:textfile=texts/t0.txt" in graph
    assert f"[{video}]" in graph or video == "ov0"
    assert audio == "afinal"
    # Không được có đường dẫn tuyệt đối trong đồ thị.
    import re

    # Không có ổ đĩa Windows hay thư mục người dùng nào trong đồ thị.
    assert re.search(r"[A-Za-z]:[\\/]", graph) is None
    assert "Users" not in graph


def test_graph_mixes_voice_with_ducked_music_when_original_kept():
    job = _job(
        keep_audio=True,
        music_file="music/a.mp3",
        voice_files=[(1.0, "voice/v0.mp3")],
    )
    graph, _video, _audio = build_filter_graph(job)
    assert "sidechaincompress" in graph
    assert "adelay=1000|1000" in graph
    # Ảnh chụp đầu vào: nhạc là input 1, lời đọc là input 2.
    assert "[2:a]" in graph and "[1:a]" in graph


def test_silent_job_has_no_audio_label():
    _graph, _video, audio = build_filter_graph(_job())
    assert audio is None


@pytest.mark.skipif(not HAS_FFMPEG, reason="cần ffmpeg và ffprobe trong PATH")
def test_end_to_end_render_produces_expected_duration(tmp_path):
    job_dir = tmp_path / "job"
    (job_dir / "input").mkdir(parents=True)
    src = job_dir / "input" / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=6:size=640x360:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=6",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(src),
        ],
        check=True,
    )
    # Lời đọc giả lập: một tone ngắn, đúng vai trò của file TTS.
    voice = job_dir / "voice" / "v0.wav"
    voice.parent.mkdir()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=600:duration=1",
            str(voice),
        ],
        check=True,
    )
    settings = load_settings()
    job = RenderJob(
        source="input/source.mp4",
        pieces=[Piece(0, 2, 0), Piece(3, 5, 2)],
        output_seconds=4,
        width=540,
        height=960,
        fps=25,
        keep_audio=True,
        texts=[TextOverlay(text="Thử nghiệm dựng", start=0, end=2, position="bottom")],
        subtitles=[Subtitle(2, 3, "phụ đề thử")],
        voice_files=[(2.5, "voice/v0.wav")],
        output="final.mp4",
    )
    out = render("ffmpeg", job_dir, job, settings.font_file)
    info = probe("ffprobe", out)
    assert abs(info.duration - 4.0) < 0.2
    assert info.has_audio
    assert (info.width, info.height) == (540, 960)
