from edit_agent.refine import _place_texts
from edit_agent.spec import EditPlan, Segment, TextOverlay


def test_place_texts_follows_segment_choice():
    plan = EditPlan(
        segments=[Segment(src_start=0, src_end=2), Segment(src_start=10, src_end=12)],
        texts=[
            TextOverlay(text="Một", start=0.2, end=1.8, position="bottom"),
            TextOverlay(text="Hai", start=2.2, end=3.8, position="bottom"),
        ],
    )
    out = _place_texts(plan, {1: "top"})
    assert [t.position for t in out] == ["bottom", "top"]
