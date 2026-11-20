from edit_agent.motion import Style, caption_filters, caption_variants, title_filter, word_reveal_times
from edit_agent.policy import Subtitle
from edit_agent.spec import TextOverlay

STYLE = Style(width=1440, height=2560, font="font.ttf", font_bold="font_bold.ttf")


def test_title_uses_bold_font_and_entrance_expressions():
    f = title_filter(0, TextOverlay(text="Chào", start=1.0, end=4.0, position="top"), STYLE)
    assert "fontfile=font_bold.ttf" in f
    assert "textfile=texts/t0.txt" in f
    # Hiện dần: độ mờ và vị trí đổi theo t; dấu phẩy đã escape.
    assert "alpha=min(clip((t-1.000)/0.40\\,0\\,1)" in f
    assert "enable='between(t,1.000,4.000)'" in f
    assert "boxcolor=0xE8A87C@0.92" in f


def test_title_without_bold_font_falls_back_to_regular():
    style = Style(width=1440, height=2560, font="font.ttf", font_bold=None)
    f = title_filter(0, TextOverlay(text="x", start=0, end=2, position="bottom"), style)
    assert "fontfile=font.ttf" in f


def test_word_reveal_is_monotonic_and_spans_the_line():
    sub = Subtitle(start=2.0, end=6.0, text="Bộ đồ mặc nhà cho bé")
    times = word_reveal_times(sub)
    assert len(times) == 6
    assert times[0] == 2.0
    assert all(a < b for a, b in zip(times, times[1:], strict=False))
    assert times[-1] < 6.0


def test_caption_variants_grow_word_by_word():
    sub = Subtitle(start=0.0, end=3.0, text="Áo in họa tiết")
    variants = caption_variants(0, sub)
    assert [rel for _s, _e, rel in variants] == [
        "texts/s0_1.txt",
        "texts/s0_2.txt",
        "texts/s0_3.txt",
        "texts/s0_4.txt",
    ]
    # Bước cuối giữ đến hết câu.
    assert variants[-1][1] == 3.0
    filters = caption_filters(0, sub, STYLE, variants)
    assert len(filters) == 4
    assert all("left" not in f and "x=115" in f for f in filters)
