from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = PROJECT_ROOT / "samples" / "tra_demo" / "manifest.json"
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm"}


def test_sample_manifest_contract() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["discipline"] == "TRA"
    assert manifest["scope"] == "single_person_demo"
    assert manifest["videos"]

    for video in manifest["videos"]:
        video_path = PROJECT_ROOT / video["path"]
        fixture_dir = PROJECT_ROOT / video["fixture_dir"]

        assert video_path.exists()
        assert video_path.suffix.lower() in ALLOWED_VIDEO_EXTENSIONS
        assert fixture_dir.is_dir()

        for expected_output in video["expected_outputs"]:
            assert (PROJECT_ROOT / expected_output).exists()
