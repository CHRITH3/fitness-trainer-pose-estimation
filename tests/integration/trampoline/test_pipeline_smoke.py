from __future__ import annotations

import json
from pathlib import Path

from trampoline.pipeline import analyze_video


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_VIDEO = PROJECT_ROOT / "samples" / "tra_demo" / "sample01.mp4"


def test_pipeline_smoke_generates_non_empty_landmarks(tmp_path: Path) -> None:
    output_dir = tmp_path / "sample01"

    analysis = analyze_video(
        video_path=SAMPLE_VIDEO,
        output_dir=output_dir,
        landmarks_only=True,
        analysis_id="sample01",
    )

    landmarks_path = output_dir / "landmarks.jsonl"
    assert analysis.analysis_id == "sample01"
    assert landmarks_path.is_file()

    rows = [
        json.loads(line)
        for line in landmarks_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    assert rows[0]["timestamp_ms"] == 0
    assert rows[-1]["timestamp_ms"] > rows[0]["timestamp_ms"]
    assert any(row["has_landmarks"] for row in rows)
