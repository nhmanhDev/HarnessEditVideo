from pathlib import Path

from edit_agent.voicecheck import best_take, similarity, spoken


def test_spoken_numbers_percent_and_letters():
    assert spoken("giảm đến 50%") == "giảm đến năm mươi phần trăm"
    assert spoken("Áo trắng số 33") == "Áo trắng số ba mươi ba"
    assert spoken("Áo đỏ chữ B") == "Áo đỏ chữ bê"
    assert spoken("21 và 15") == "hai mươi mốt và mười lăm"
    assert spoken("105") == "một trăm lẻ năm"


def test_similarity_treats_digits_and_words_alike():
    assert similarity("giảm 50%", "giảm năm mươi phần trăm") > 0.95


def test_similarity_ignores_accents_and_punctuation():
    assert similarity("Áo đỏ, quần jean.", "ao do quan jean") > 0.95


def test_similarity_low_for_different_text():
    assert similarity("Áo kem chân váy xanh rêu", "Àu hóa không vậy đó") < 0.5


def test_best_take_keeps_best_and_cleans_up(tmp_path: Path):
    heard = iter(["sai hoan toan", "ao do quan jean", "ao do quan"])
    written: list[Path] = []

    def synth(text: str, out: Path) -> None:
        out.write_bytes(f"take{len(written)}".encode())
        written.append(out)

    out = tmp_path / "v.mp3"
    score = best_take(synth, lambda p: next(heard), "Áo đỏ quần jean", out, tries=3, accept=0.99)
    assert score > 0.95
    assert out.read_bytes() == b"take1"  # lần thứ hai khớp nhất
    assert not list(tmp_path.glob("*.take*"))


def test_best_take_stops_early_when_good_enough(tmp_path: Path):
    calls = []

    def synth(text: str, out: Path) -> None:
        calls.append(out)
        out.write_bytes(b"x")

    best_take(synth, lambda p: "áo đỏ", "Áo đỏ", tmp_path / "v.mp3", tries=3, accept=0.9)
    assert len(calls) == 1


def test_single_try_skips_asr(tmp_path: Path):
    def boom(p: Path) -> str:
        raise AssertionError("không được nghe lại khi tries=1")

    best_take(lambda t, o: o.write_bytes(b"x"), boom, "Áo", tmp_path / "v.mp3", tries=1)
    assert (tmp_path / "v.mp3").exists()
