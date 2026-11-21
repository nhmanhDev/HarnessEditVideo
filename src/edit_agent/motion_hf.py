"""Lớp chữ chuyển động bằng HyperFrames (HTML + GSAP, dựng bằng Chrome không giao diện), xuất WebM trong suốt.

Tiêu đề: từng từ nảy vào, từ nhấn đổi màu, thanh nhấn quét dưới chữ, mờ ra khi hết.
Phụ đề: cả câu hiện dần, từ đang đọc phóng nhẹ và đổi màu (kiểu karaoke).

Lớp này được ghép lên video bằng ffmpeg. Nếu không có Node/npx, không có mạng (GSAP lấy từ CDN) hoặc dựng lỗi,
trả về None để harness dùng lại chữ drawtext trong motion.py.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

from .config import REPO_ROOT
from .motion import word_reveal_times
from .policy import Subtitle
from .spec import TextOverlay

HF_VERSION = "0.9.72"
ACCENT = "#E8A87C"
HILITE = "#FFD166"
_MARK = re.compile(r"\*(.+?)\*")


def strip_markup(text: str) -> str:
    """Bỏ dấu * đánh dấu từ nhấn, dùng cho chữ drawtext dự phòng."""
    return _MARK.sub(r"\1", text)


def _words_html(text: str) -> str:
    """Chia thành từ; từ nằm trong *...* là từ nhấn."""
    out: list[str] = []
    pos = 0
    for m in _MARK.finditer(text):
        out += [("w", w) for w in text[pos : m.start()].split()]
        out += [("hi", w) for w in m.group(1).split()]
        pos = m.end()
    out += [("w", w) for w in text[pos:].split()]
    return "".join(f'<span class="word{" hi" if kind == "hi" else ""}">{html.escape(w)}</span>' for kind, w in out)


_POS_TOP = {"top": "300px", "center": "1000px", "bottom": "1650px"}


def build_html(
    texts: list[TextOverlay],
    subtitles: list[Subtitle],
    duration: float,
    width: int = 1440,
    height: int = 2560,
) -> str:
    scale = width / 1440
    blocks: list[str] = []
    js: list[str] = []

    for i, t in enumerate(texts):
        top = _POS_TOP[t.position]
        # Cỡ chữ tự co để cả tiêu đề nằm trên một dòng (chữ Arial Black rộng khoảng 0,62 lần cỡ chữ).
        plain = t.text.replace("*", "")
        avail = width - 2 * int(90 * scale)
        size = int(max(72 * scale, min(140 * scale, avail / (0.62 * max(len(plain), 1)))))
        blocks.append(
            f'<div class="title t{i}" style="top:{top};--fs:{size}px" data-start="{t.start:.3f}" '
            f'data-duration="{max(t.end - t.start, 0.1):.3f}" data-track-index="{i}">'
            f'<div class="words">{_words_html(t.text)}</div><div class="bar b{i}"></div></div>'
        )
        end_out = max(t.start + 0.5, t.end - 0.3)
        js.append(
            f"tl.fromTo('.t{i} .word', {{opacity:0,y:90,scale:0.8,rotate:-4}},"
            f"{{opacity:1,y:0,scale:1,rotate:0,duration:0.45,ease:'back.out(2.2)',stagger:0.09}},{t.start:.3f}+0.05);"
            f"tl.to('.b{i}', {{scaleX:1,duration:0.5,ease:'power3.out'}},{t.start:.3f}+0.45);"
            f"tl.to(['.t{i} .word', '.b{i}'], {{opacity:0,y:-40,duration:0.3,ease:'power2.in',stagger:0.03}},{end_out:.3f});"
        )

    base = len(texts)
    for j, s in enumerate(subtitles):
        words = s.text.split()
        times = word_reveal_times(s)
        spans = "".join(f'<span class="cw">{html.escape(w)}</span>' for w in words)
        blocks.append(
            f'<div class="cap c{j}" data-start="{s.start:.3f}" data-duration="{max(s.end - s.start, 0.1):.3f}" '
            f'data-track-index="{base + j}"><div class="cwords">{spans}</div></div>'
        )
        for k, tk in enumerate(times):
            nxt = times[k + 1] if k + 1 < len(times) else s.end
            sel = f".c{j} .cw:nth-child({k + 1})"
            js.append(
                f"tl.fromTo('{sel}', {{opacity:0,y:28}}, {{opacity:1,y:0,duration:0.18,ease:'power2.out'}},{max(tk - 0.04, 0):.3f});"
                f"tl.to('{sel}', {{color:'{HILITE}',scale:1.14,duration:0.12,ease:'back.out(3)'}},{tk:.3f});"
                f"tl.to('{sel}', {{color:'#ffffff',scale:1,duration:0.18}},{nxt:.3f});"
            )
        js.append(f"tl.to('.c{j} .cw', {{opacity:0,duration:0.2}},{max(s.end - 0.2, s.start + 0.1):.3f});")

    css = f"""
      * {{ margin:0; padding:0; box-sizing:border-box; }}
      html, body {{ width:{width}px; height:{height}px; overflow:hidden; background:transparent; }}
      #root {{ position:relative; width:{width}px; height:{height}px; font-family:"Arial Black", Arial, sans-serif; }}
      .title {{ position:absolute; left:0; right:0; text-align:center; padding:0 {int(90 * scale)}px; }}
      .words {{ display:flex; justify-content:center; flex-wrap:wrap; gap:0 {int(28 * scale)}px; }}
      .words {{ flex-wrap:nowrap; }}
      .word {{ display:inline-block; font-size:var(--fs, {int(140 * scale)}px); white-space:nowrap; font-weight:900; color:#fff; line-height:1.12;
               text-shadow:0 8px 30px rgba(0,0,0,0.5); opacity:0; }}
      .word.hi {{ color:{HILITE}; }}
      .bar {{ margin:{int(18 * scale)}px auto 0; width:{int(760 * scale)}px; height:{int(16 * scale)}px; background:{ACCENT};
              border-radius:9px; transform-origin:left center; transform:scaleX(0); }}
      .cap {{ position:absolute; left:0; right:0; top:{int(1800 * scale)}px; text-align:center; padding:0 {int(110 * scale)}px; }}
      .cwords {{ display:flex; justify-content:center; flex-wrap:wrap; gap:0 {int(22 * scale)}px; }}
      .cw {{ display:inline-block; font-size:{int(96 * scale)}px; font-weight:900; color:#fff; line-height:1.2; opacity:0;
             text-shadow:0 6px 24px rgba(0,0,0,0.65); -webkit-text-stroke:2px rgba(0,0,0,0.35); }}
    """
    return (
        '<!doctype html>\n<html lang="vi">\n<head>\n<meta charset="UTF-8" />\n'
        f'<meta name="viewport" content="width={width}, height={height}" />\n'
        '<script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>\n'
        f"<style>{css}</style>\n</head>\n<body>\n"
        f'<div id="root" data-composition-id="main" data-start="0" data-duration="{duration:.3f}" '
        f'data-width="{width}" data-height="{height}">\n' + "\n".join(blocks) + "\n</div>\n<script>\n"
        "const tl = gsap.timeline({ paused: true });\n" + "\n".join(js) + "\n"
        'window.__timelines["main"] = tl;\ntl.seek(0);\n</script>\n</body>\n</html>\n'
    )


def render_overlay(
    job_dir: Path,
    texts: list[TextOverlay],
    subtitles: list[Subtitle],
    duration: float,
    width: int,
    height: int,
    fps: int = 30,
    timeout: int = 1500,
) -> str | None:
    """Dựng overlay.webm trong suốt. Trả về tên file tương đối trong thư mục job, hoặc None nếu không dựng được."""
    npx = shutil.which("npx")
    if not npx or not (texts or subtitles):
        return None
    hf = job_dir / "hf"
    hf.mkdir(exist_ok=True)
    for name in ("hyperframes.json", "meta.json"):
        shutil.copy2(REPO_ROOT / "templates" / "hyperframes" / name, hf / name)
    page = build_html(texts, subtitles, duration, width, height)
    (hf / "index.html").write_text(page, encoding="utf-8")
    (hf / "package.json").write_text(
        json.dumps({"name": "overlay", "private": True, "type": "module"}), encoding="utf-8"
    )
    out = "overlay.webm"
    # Cùng nội dung chữ và độ dài thì dùng lại lớp đã dựng (mỗi lần dựng mất vài chục giây).
    key = hashlib.sha1(f"{page}|{fps}".encode()).hexdigest()
    marker = job_dir / "overlay.key"
    if (job_dir / out).exists() and marker.exists() and marker.read_text(encoding="utf-8") == key:
        return out
    try:
        proc = subprocess.run(
            [
                npx,
                "--yes",
                f"hyperframes@{HF_VERSION}",
                "render",
                ".",
                "--format",
                "webm",
                "-o",
                f"../{out}",
                "--fps",
                str(fps),
                "--quiet",
            ],
            cwd=hf,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0 or not (job_dir / out).exists():
        return None
    marker.write_text(key, encoding="utf-8")
    return out
