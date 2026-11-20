"""Chọn bản đọc tốt nhất: tổng hợp một câu vài lần, nhận dạng lại, giữ bản khớp lời viết nhất.

TTS lấy mẫu ngẫu nhiên nên cùng một câu lúc đọc đúng lúc đọc sai; kiểm bằng nhận dạng giọng nói rẻ hơn nhiều so với
để người nghe bản sai.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections.abc import Callable
from pathlib import Path


def _strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", _strip_accents(text).lower())


def similarity(want: str, heard: str) -> float:
    """Độ khớp 0..1 giữa lời viết và lời nghe lại; không tính dấu vì nhận dạng tiếng Việt hay sai dấu."""
    a, b = _words(want), _words(heard)
    if not a or not b:
        return 0.0
    word = difflib.SequenceMatcher(None, a, b).ratio()
    char = difflib.SequenceMatcher(None, "".join(a), "".join(b)).ratio()
    return 0.5 * word + 0.5 * char


def best_take(
    synth: Callable[[str, Path], None],
    asr: Callable[[Path], str],
    text: str,
    out: Path,
    tries: int = 3,
    accept: float = 0.9,
) -> float:
    """Ghi bản tốt nhất vào `out`, trả về độ khớp. Dừng sớm khi một bản đạt `accept`."""
    best_score, best_path = -1.0, None
    takes: list[Path] = []
    for k in range(max(1, tries)):
        take = out.with_name(f"{out.stem}.take{k}{out.suffix}")
        synth(text, take)
        takes.append(take)
        score = similarity(text, asr(take)) if tries > 1 else 1.0
        if score > best_score:
            best_score, best_path = score, take
        if score >= accept:
            break
    assert best_path is not None
    best_path.replace(out)
    for t in takes:
        if t.exists():
            t.unlink()
    return best_score
