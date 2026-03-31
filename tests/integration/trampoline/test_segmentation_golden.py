from __future__ import annotations

import shutil
from pathlib import Path

from trampoline.bounce_segmenter import segment_analysis_dir


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_ANALYSIS_DIR = PROJECT_ROOT / "artifacts" / "trampoline" / "sample01"


def test_segmentation_golden_for_sample01(tmp_path: Path) -> None:
    analysis_dir = tmp_path / "sample01"
    shutil.copytree(SAMPLE_ANALYSIS_DIR, analysis_dir)

    segmentation = segment_analysis_dir(analysis_dir)
    jump_segments = segmentation["jump_segments"]

    assert (analysis_dir / "segmentation.json").is_file()
    assert len(segmentation["contact_candidates"]) >= 3
    assert len(segmentation["apex_candidates"]) >= 3
    assert len(jump_segments) == 2
    assert [(segment["start_ms"], segment["apex_ms"], segment["end_ms"]) for segment in jump_segments] == [
        (750, 1333, 1583),
        (1583, 1792, 2375),
    ]
    for segment in jump_segments:
        assert segment["start_ms"] <= segment["takeoff_ms"] <= segment["apex_ms"] <= segment["landing_ms"] <= segment["end_ms"]

