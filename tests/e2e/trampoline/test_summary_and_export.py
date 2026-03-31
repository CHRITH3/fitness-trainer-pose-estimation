from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from app import app, trampoline_analyses
from trampoline.pipeline import sync_phase3_artifacts


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_ANALYSIS_DIR = PROJECT_ROOT / "artifacts" / "trampoline" / "sample01"


def test_summary_panel_and_export_bundle_are_available(tmp_path: Path) -> None:
    analysis_id = "sample01"
    artifacts_dir = tmp_path / "artifacts"
    analysis_dir = artifacts_dir / analysis_id
    shutil.copytree(SAMPLE_ANALYSIS_DIR, analysis_dir)
    sync_phase3_artifacts(analysis_dir)

    app.config["TESTING"] = True
    app.config["TRAMPOLINE_UPLOAD_DIR"] = tmp_path / "uploads"
    app.config["TRAMPOLINE_ARTIFACTS_DIR"] = artifacts_dir
    trampoline_analyses.clear()
    client = app.test_client()

    result_response = client.get(f"/api/trampoline/result/{analysis_id}")
    result_payload = result_response.get_json()
    assert result_response.status_code == 200
    assert result_payload["result"]["routine_summary"]["jump_count"] >= 1
    assert result_payload["result"]["landing"]["jumps"][0]["landing_source"]

    page_response = client.get(f"/trampoline?analysis_id={analysis_id}")
    html = page_response.get_data(as_text=True)
    assert page_response.status_code == 200
    assert 'id="summary-panel"' in html
    assert 'id="landing-heatmap"' in html
    assert 'id="export-analysis"' in html
    assert '"routine_summary"' in html

    export_response = client.get(f"/api/trampoline/export/{analysis_id}")
    assert export_response.status_code == 200
    assert export_response.mimetype == "application/zip"

    bundle_path = tmp_path / "downloaded_bundle.zip"
    bundle_path.write_bytes(export_response.data)
    with zipfile.ZipFile(bundle_path) as archive:
        names = set(archive.namelist())

    assert "summary.md" in names
    assert "analysis.json" in names
    assert "overlays/landing_heatmap.json" in names
