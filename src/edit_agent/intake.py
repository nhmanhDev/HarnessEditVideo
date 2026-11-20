"""Nhận video đầu vào: link Google Drive (công khai) hoặc đường dẫn cục bộ."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from .config import Settings

_DRIVE_HOSTS = ("drive.google.com", "docs.google.com")


def is_drive_link(value: str) -> bool:
    return value.startswith("http") and any(h in value for h in _DRIVE_HOSTS)


def new_job_dir(settings: Settings, label: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40] or "job"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    job = settings.jobs_dir / f"{stamp}-{slug}"
    job.mkdir(parents=True, exist_ok=False)
    return job


def fetch_source(value: str, job_dir: Path) -> Path:
    """Đưa video nguồn vào thư mục job, đặt tên source.<đuôi>."""
    dst_dir = job_dir / "input"
    dst_dir.mkdir(parents=True, exist_ok=True)

    if is_drive_link(value):
        import gdown

        out = dst_dir / "source.mp4"
        result = gdown.download(url=value, output=str(out), quiet=False, fuzzy=True)
        if not result or not out.exists():
            raise RuntimeError(
                "Không tải được file từ Drive. File phải để 'Bất kỳ ai có đường liên kết' (công khai). "
                "File riêng tư cần tài khoản dịch vụ, chưa hỗ trợ ở bản này."
            )
        return out

    src = Path(value).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"Không thấy file đầu vào: {src.name}")
    out = dst_dir / f"source{src.suffix.lower() or '.mp4'}"
    shutil.copy2(src, out)
    return out
