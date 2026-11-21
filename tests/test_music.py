import json

from edit_agent.music import load_tracks


def test_tracks_without_license_or_file_are_ignored(tmp_path):
    (tmp_path / "ok.mp3").write_bytes(b"x")
    (tmp_path / "no-license.mp3").write_bytes(b"x")
    manifest = {
        "tracks": [
            {"id": "ok", "file": "ok.mp3", "license": "CC0", "source": "nguồn A"},
            {"id": "no-license", "file": "no-license.mp3", "license": "", "source": "nguồn B"},
            {"id": "missing", "file": "missing.mp3", "license": "CC0", "source": "nguồn C"},
        ]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    tracks = load_tracks(tmp_path)
    assert list(tracks) == ["ok"]
    assert tracks["ok"].license == "CC0"


def test_missing_manifest_gives_empty_library(tmp_path):
    assert load_tracks(tmp_path) == {}
