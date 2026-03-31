from __future__ import annotations

import time
from pathlib import Path

from app import app, trampoline_analyses


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_VIDEO = PROJECT_ROOT / "samples" / "tra_demo" / "sample01.mp4"


def test_upload_and_status_flow(tmp_path: Path) -> None:
    app.config["TESTING"] = True
    app.config["TRAMPOLINE_UPLOAD_DIR"] = tmp_path / "uploads"
    app.config["TRAMPOLINE_ARTIFACTS_DIR"] = tmp_path / "artifacts"
    trampoline_analyses.clear()

    client = app.test_client()
    with SAMPLE_VIDEO.open("rb") as video_file:
        response = client.post(
            "/api/trampoline/upload",
            data={"video": (video_file, "sample01.mp4")},
            content_type="multipart/form-data",
        )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["status"] == "uploaded"

    analysis_id = payload["analysis_id"]
    start_response = client.post("/api/trampoline/analyze", json={"analysis_id": analysis_id})
    start_payload = start_response.get_json()
    assert start_response.status_code == 202
    assert start_payload["status"] == "queued"

    final_payload = None
    for _ in range(60):
        status_response = client.get(f"/api/trampoline/status/{analysis_id}")
        final_payload = status_response.get_json()
        if final_payload["status"] == "done":
            break
        time.sleep(0.2)

    assert final_payload is not None
    assert final_payload["status"] == "done"
    assert final_payload["result"]["frames_meta"]["frame_count"] > 0
    assert final_payload["result"]["preview_frame"]["landmarks"]
    artifact_names = {artifact["name"] for artifact in final_payload["result"]["artifacts"]}
    assert {"landmarks", "frames_meta", "analysis"} <= artifact_names
