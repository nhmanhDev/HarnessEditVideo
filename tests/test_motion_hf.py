from edit_agent import motion_hf
from edit_agent.motion_hf import build_html, render_overlay, strip_markup
from edit_agent.policy import Piece, Subtitle
from edit_agent.render import RenderJob, build_filter_graph
from edit_agent.spec import TextOverlay


def test_strip_markup_removes_highlight_stars():
    assert strip_markup("Đồ mặc *nhà* cho bé") == "Đồ mặc nhà cho bé"


def test_html_has_words_highlight_and_timeline():
    page = build_html(
        [TextOverlay(text="Đồ mặc *cho bé*", start=1.0, end=4.0, position="top")],
        [],
        duration=10.0,
    )
    assert '<span class="word">Đồ</span>' in page
    assert '<span class="word hi">cho</span>' in page
    assert '<span class="word hi">bé</span>' in page
    assert 'data-duration="10.000"' in page
    assert 'window.__timelines["main"] = tl' in page


def test_html_escapes_text():
    page = build_html([TextOverlay(text="<b>x</b>", start=0, end=2, position="center")], [], duration=3.0)
    assert "<b>x</b>" not in page
    assert "&lt;b&gt;x&lt;/b&gt;" in page


def test_html_builds_karaoke_caption_per_word():
    page = build_html([], [Subtitle(start=0.0, end=3.0, text="Áo in họa tiết")], duration=3.0)
    assert page.count('class="cw"') == 4
    assert ".c0 .cw:nth-child(4)" in page


def test_overlay_returns_none_without_npx(tmp_path, monkeypatch):
    monkeypatch.setattr(motion_hf.shutil, "which", lambda _name: None)
    out = render_overlay(
        tmp_path, [TextOverlay(text="x", start=0, end=2, position="top")], [], 3.0, 1440, 2560
    )
    assert out is None


def test_overlay_is_last_input_after_music_and_voices():
    job = RenderJob(
        source="input/source.mp4",
        pieces=[Piece(0, 2, 0)],
        output_seconds=2,
        width=1440,
        height=2560,
        fps=30,
        keep_audio=False,
        voice_files=[(0.5, "voice/a.mp3"), (1.0, "voice/b.mp3")],
        music_file="music/m.mp3",
        overlay_file="overlay.webm",
    )
    graph, video, _audio = build_filter_graph(job)
    # Nguồn 0, nhạc 1, hai lời đọc 2 và 3, lớp chữ 4.
    assert "overlay=0:0:format=auto[ovhf]" in graph
    assert "[vc][4:v]overlay" in graph
    assert video == "ovhf"
    assert "drawtext" not in graph
