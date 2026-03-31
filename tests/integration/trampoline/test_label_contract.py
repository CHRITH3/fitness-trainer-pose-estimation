from __future__ import annotations

import json
import shutil
from pathlib import Path

from trampoline.pipeline import load_analysis_model, load_analysis_output, sync_phase3_artifacts


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_ANALYSIS_DIR = PROJECT_ROOT / "artifacts" / "trampoline" / "sample01"


def test_label_contract_matches_ui_payload_keys(tmp_path: Path) -> None:
    analysis_dir = tmp_path / "sample01"
    shutil.copytree(SAMPLE_ANALYSIS_DIR, analysis_dir)

    sync_phase3_artifacts(analysis_dir)

    feature_rows = [
        json.loads(line)
        for line in (analysis_dir / "features.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    labels_payload = json.loads((analysis_dir / "labels.json").read_text(encoding="utf-8"))
    analysis = load_analysis_model(analysis_dir)
    result = load_analysis_output(analysis_dir)

    assert feature_rows
    assert {
        "analysis_id",
        "jump_id",
        "frame_index",
        "timestamp_ms",
        "flight_phase",
        "is_mid_flight_window",
        "trunk_thigh_angle",
        "thigh_shank_angle",
    }.issubset(feature_rows[0].keys())

    first_label = labels_payload["labels"][0]
    assert {
        "jump_id",
        "auto_label",
        "resolved_label",
        "confidence",
        "source",
        "decision_reason",
        "fallback_reason",
        "feature_summary",
    }.issubset(first_label.keys())

    assert any(artifact.name == "features" for artifact in analysis.artifacts)
    assert any(artifact.name == "labels" for artifact in analysis.artifacts)
    assert len(result["labels"]) == len(result["jump_segments"]) == 2
    assert {
        "auto_label",
        "resolved_label",
        "label_confidence",
        "decision_reason",
        "fallback_reason",
        "feature_summary",
    }.issubset(result["jump_segments"][0].keys())
