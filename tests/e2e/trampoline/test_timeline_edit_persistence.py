from __future__ import annotations

import json
import shutil
from pathlib import Path

from app import app, trampoline_analyses


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_ANALYSIS_DIR = PROJECT_ROOT / "artifacts" / "trampoline" / "sample01"


def test_timeline_edit_persistence_round_trip(tmp_path: Path) -> None:
    analysis_id = "sample01"
    artifacts_dir = tmp_path / "artifacts"
    shutil.copytree(SAMPLE_ANALYSIS_DIR, artifacts_dir / analysis_id)

    app.config["TESTING"] = True
    app.config["TRAMPOLINE_UPLOAD_DIR"] = tmp_path / "uploads"
    app.config["TRAMPOLINE_ARTIFACTS_DIR"] = artifacts_dir
    trampoline_analyses.clear()
    client = app.test_client()

    initial_result = client.get(f"/api/trampoline/result/{analysis_id}").get_json()["result"]
    auto_segments = initial_result["jump_segments"]
    assert len(auto_segments) == 2

    split_payload = {
        "jump_segments": [
            {
                "jump_id": "jump-001a",
                "sequence_index": 0,
                "start_ms": 750,
                "takeoff_ms": 920,
                "apex_ms": 1080,
                "landing_ms": 1170,
                "end_ms": 1200,
                "source": "merged",
                "auto_jump_ids": ["jump-001"],
                "manual_boundary_fields": ["start_ms", "takeoff_ms", "apex_ms", "landing_ms", "end_ms"],
            },
            {
                "jump_id": "jump-001b",
                "sequence_index": 1,
                "start_ms": 1200,
                "takeoff_ms": 1320,
                "apex_ms": 1440,
                "landing_ms": 1540,
                "end_ms": 1583,
                "source": "merged",
                "auto_jump_ids": ["jump-001"],
                "manual_boundary_fields": ["start_ms", "takeoff_ms", "apex_ms", "landing_ms", "end_ms"],
            },
            {
                **auto_segments[1],
                "sequence_index": 2,
            },
        ]
    }
    split_response = client.post(f"/api/trampoline/overrides/{analysis_id}", json=split_payload)
    split_json = split_response.get_json()
    assert split_response.status_code == 200
    assert split_json["success"] is True
    assert len(split_json["result"]["jump_segments"]) == 3
    assert any(item["operation"] == "replace_segments" for item in split_json["overrides"]["manual_overrides"])
    assert any(item["operation"] == "split_jump" for item in split_json["overrides"]["manual_overrides"])

    persisted_split = client.get(f"/api/trampoline/result/{analysis_id}").get_json()["result"]
    assert len(persisted_split["jump_segments"]) == 3

    merge_payload = {
        "jump_segments": [
            {
                "jump_id": "jump-001m",
                "sequence_index": 0,
                "start_ms": 750,
                "takeoff_ms": 980,
                "apex_ms": 1320,
                "landing_ms": 1550,
                "end_ms": 1583,
                "source": "merged",
                "auto_jump_ids": ["jump-001"],
                "manual_boundary_fields": ["takeoff_ms", "apex_ms", "landing_ms"],
            },
            {
                **auto_segments[1],
                "sequence_index": 1,
            },
        ]
    }
    merge_response = client.post(f"/api/trampoline/overrides/{analysis_id}", json=merge_payload)
    merge_json = merge_response.get_json()
    assert merge_response.status_code == 200
    assert merge_json["success"] is True
    assert len(merge_json["result"]["jump_segments"]) == 2
    assert merge_json["result"]["jump_segments"][0]["landing_ms"] == 1550

    overrides_path = artifacts_dir / analysis_id / "overrides.json"
    overrides_payload = json.loads(overrides_path.read_text(encoding="utf-8"))
    assert any(item["operation"] == "update_boundary" for item in overrides_payload["manual_overrides"])

    reloaded = client.get(f"/api/trampoline/result/{analysis_id}").get_json()["result"]
    assert reloaded["jump_segments"][0]["landing_ms"] == 1550
    page_html = client.get(f"/trampoline?analysis_id={analysis_id}").get_data(as_text=True)
    assert '"landing_ms": 1550' in page_html
