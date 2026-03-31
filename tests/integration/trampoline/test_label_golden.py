from __future__ import annotations

import shutil
from pathlib import Path

from trampoline.pipeline import sync_phase3_artifacts


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_ANALYSIS_DIR = PROJECT_ROOT / "artifacts" / "trampoline" / "sample01"


def test_label_golden_for_sample01(tmp_path: Path) -> None:
    analysis_dir = tmp_path / "sample01"
    shutil.copytree(SAMPLE_ANALYSIS_DIR, analysis_dir)
    (analysis_dir / "features.jsonl").unlink(missing_ok=True)
    (analysis_dir / "labels.json").unlink(missing_ok=True)

    labels_artifact = sync_phase3_artifacts(analysis_dir)

    assert (analysis_dir / "features.jsonl").is_file()
    assert (analysis_dir / "labels.json").is_file()
    assert [(item.jump_id, item.auto_label, item.resolved_label) for item in labels_artifact.labels] == [
        ("jump-001", "pike", "pike"),
        ("jump-002", "tuck", "tuck"),
    ]
    assert labels_artifact.labels[0].confidence >= 0.9
    assert labels_artifact.labels[1].confidence >= 0.6
