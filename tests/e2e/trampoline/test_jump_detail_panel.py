from __future__ import annotations

import shutil
from pathlib import Path

from app import app, trampoline_analyses
from trampoline.pipeline import sync_phase3_artifacts


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_ANALYSIS_DIR = PROJECT_ROOT / "artifacts" / "trampoline" / "sample01"


def test_jump_detail_panel_contract_is_exposed_on_page(tmp_path: Path) -> None:
    analysis_id = "sample01"
    artifacts_dir = tmp_path / "artifacts"
    shutil.copytree(SAMPLE_ANALYSIS_DIR, artifacts_dir / analysis_id)
    sync_phase3_artifacts(artifacts_dir / analysis_id)

    app.config["TESTING"] = True
    app.config["TRAMPOLINE_UPLOAD_DIR"] = tmp_path / "uploads"
    app.config["TRAMPOLINE_ARTIFACTS_DIR"] = artifacts_dir
    trampoline_analyses.clear()
    client = app.test_client()

    result_response = client.get(f"/api/trampoline/result/{analysis_id}")
    result_json = result_response.get_json()
    assert result_response.status_code == 200
    assert result_json["result"]["jump_segments"][0]["auto_label"] == "pike"
    assert result_json["result"]["jump_segments"][0]["decision_reason"]

    page_response = client.get(f"/trampoline?analysis_id={analysis_id}")
    html = page_response.get_data(as_text=True)
    js = (PROJECT_ROOT / "static" / "js" / "trampoline.js").read_text(encoding="utf-8")

    assert page_response.status_code == 200
    assert 'id="jump-detail-card"' in html
    assert 'id="jump-auto-label"' in html
    assert 'id="jump-decision-reason"' in html
    assert '"auto_label": "pike"' in html
    assert "jumpDecisionReason.textContent = segment.decision_reason" in js
    assert "previewVideo.currentTime = segment.start_ms / 1000" in js
