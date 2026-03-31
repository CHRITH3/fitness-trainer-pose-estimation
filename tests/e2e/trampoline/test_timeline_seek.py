from __future__ import annotations

import shutil
from pathlib import Path

from app import app, trampoline_analyses


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_ANALYSIS_DIR = PROJECT_ROOT / "artifacts" / "trampoline" / "sample01"


def test_timeline_seek_contract_is_exposed_on_page(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    shutil.copytree(SAMPLE_ANALYSIS_DIR, artifacts_dir / "sample01")

    app.config["TESTING"] = True
    app.config["TRAMPOLINE_UPLOAD_DIR"] = tmp_path / "uploads"
    app.config["TRAMPOLINE_ARTIFACTS_DIR"] = artifacts_dir
    trampoline_analyses.clear()
    client = app.test_client()

    result_response = client.get("/api/trampoline/result/sample01")
    result_json = result_response.get_json()
    assert result_response.status_code == 200
    assert len(result_json["result"]["jump_segments"]) == 2
    assert result_json["result"]["jump_segments"][0]["start_ms"] == 750

    page_response = client.get("/trampoline?analysis_id=sample01")
    html = page_response.get_data(as_text=True)
    js = (PROJECT_ROOT / "static" / "js" / "trampoline.js").read_text(encoding="utf-8")

    assert page_response.status_code == 200
    assert 'id="timeline-track"' in html
    assert 'id="jump-editor-form"' in html
    assert '"jump_segments"' in html
    assert "previewVideo.currentTime = segment.start_ms / 1000" in js
    assert 'timeline-block current' in js or 'timeline-block.current' in (PROJECT_ROOT / "static" / "css" / "trampoline.css").read_text(encoding="utf-8")

