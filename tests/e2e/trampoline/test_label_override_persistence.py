from __future__ import annotations

import json
import shutil
from pathlib import Path

from app import app, trampoline_analyses
from trampoline.pipeline import sync_phase3_artifacts


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_ANALYSIS_DIR = PROJECT_ROOT / "artifacts" / "trampoline" / "sample01"


def test_label_override_persistence_round_trip(tmp_path: Path) -> None:
    analysis_id = "sample01"
    artifacts_dir = tmp_path / "artifacts"
    shutil.copytree(SAMPLE_ANALYSIS_DIR, artifacts_dir / analysis_id)
    sync_phase3_artifacts(artifacts_dir / analysis_id)

    app.config["TESTING"] = True
    app.config["TRAMPOLINE_UPLOAD_DIR"] = tmp_path / "uploads"
    app.config["TRAMPOLINE_ARTIFACTS_DIR"] = artifacts_dir
    trampoline_analyses.clear()
    client = app.test_client()

    override_response = client.post(
        f"/api/trampoline/labels/{analysis_id}",
        json={
            "jump_id": "jump-001",
            "override_label": "tuck",
            "override_note": "manual review",
        },
    )
    override_json = override_response.get_json()
    assert override_response.status_code == 200
    assert override_json["result"]["jump_segments"][0]["resolved_label"] == "tuck"
    assert override_json["result"]["jump_segments"][0]["override_note"] == "manual review"

    reloaded = client.get(f"/api/trampoline/result/{analysis_id}").get_json()["result"]
    assert reloaded["jump_segments"][0]["resolved_label"] == "tuck"
    assert reloaded["jump_segments"][0]["override_label"] == "tuck"

    labels_payload = json.loads((artifacts_dir / analysis_id / "labels.json").read_text(encoding="utf-8"))
    assert labels_payload["labels"][0]["override_label"] == "tuck"
    assert labels_payload["labels"][0]["override_note"] == "manual review"

    clear_response = client.post(
        f"/api/trampoline/labels/{analysis_id}",
        json={"jump_id": "jump-001", "override_label": None, "override_note": ""},
    )
    clear_json = clear_response.get_json()
    assert clear_response.status_code == 200
    assert clear_json["result"]["jump_segments"][0]["resolved_label"] == "pike"
    assert clear_json["result"]["jump_segments"][0]["override_label"] is None

    page_html = client.get(f"/trampoline?analysis_id={analysis_id}").get_data(as_text=True)
    assert '"resolved_label": "pike"' in page_html
