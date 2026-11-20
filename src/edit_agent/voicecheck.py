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

_DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_LETTERS = {
    "a": "a", "b": "bê", "c": "xê", "d": "đê", "e": "e", "f": "ép", "g": "gờ", "h": "hát", "i": "i", "k": "ca",
    "l": "lờ", "m": "mờ", "n": "nờ", "o": "o", "p": "pê", "q": "quy", "r": "rờ", "s": "ét", "t": "tê", "u": "u",
    "v": "vê", "x": "ích", "y": "i", "z": "dét",
}  # fmt: skip


def _number_words(n: int) -> str:
    """Số 0..999 đọc tiếng Việt; số lớn hơn đọc từng chữ số."""
    if n >= 1000:
        return " ".join(_DIGITS[int(d)] for d in str(n))
    if n < 10:
        return _DIGITS[n]
    if n < 100:
        tens, unit = divmod(n, 10)
        head = "mười" if tens == 1 else f"{_DIGITS[tens]} mươi"
        if unit == 0:
            return head
        tail = {1: "mốt", 5: "lăm"}.get(unit, _DIGITS[unit]) if tens > 1 else ("lăm" if unit == 5 else _DIGITS[unit])
        return f"{head} {tail}"
    hundreds, rest = divmod(n, 100)
    head = f"{_DIGITS[hundreds]} trăm"
    if rest == 0:
        return head
    if rest < 10:
        return f"{head} lẻ {_DIGITS[rest]}"
    return f"{head} {_number_words(rest)}"


def spoken(text: str) -> str:
    """Dạng đọc được của câu: số thành chữ, % thành phần trăm, chữ cái đứng một mình đọc theo tên chữ."""
    text = re.sub(r"(\d+)\s*%", lambda m: f"{_number_words(int(m.group(1)))} phần trăm", text)
    text = re.sub(r"\d+", lambda m: _number_words(int(m.group(0))), text)
    return re.sub(r"(?<![\w])([A-Za-z])(?![\w])", lambda m: _LETTERS.get(m.group(1).lower(), m.group(1)), text)


def _strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", _strip_accents(text).lower())


def similarity(want: str, heard: str) -> float:
    """Độ khớp 0..1 giữa lời viết và lời nghe lại; không tính dấu vì nhận dạng tiếng Việt hay sai dấu."""
    a, b = _words(spoken(want)), _words(spoken(heard))
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
    said = spoken(text)  # TTS đọc dạng chữ; phụ đề vẫn dùng câu gốc
    for k in range(max(1, tries)):
        take = out.with_name(f"{out.stem}.take{k}{out.suffix}")
        synth(said, take)
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
