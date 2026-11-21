"""Thư viện nhạc: chỉ dùng bản có ghi giấy phép trong manifest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Track:
    id: str
    file: Path
    license: str
    source: str


def load_tracks(music_dir: Path) -> dict[str, Track]:
    manifest = music_dir / "manifest.json"
    if not manifest.exists():
        return {}
    data = json.loads(manifest.read_text(encoding="utf-8"))
    tracks: dict[str, Track] = {}
    for item in data.get("tracks", []):
        # Thiếu giấy phép thì không đưa vào thư viện: không dùng nhạc mà không biết quyền sử dụng.
        if not item.get("license") or not item.get("source"):
            continue
        track = Track(
            id=item["id"],
            file=music_dir / item["file"],
            license=item["license"],
            source=item["source"],
        )
        if track.file.exists():
            tracks[track.id] = track
    return tracks
